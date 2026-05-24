import asyncio
import json
import logging
import os
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urlencode

import discord
import feedparser
import requests
from discord import app_commands
from discord.ext import tasks
from dotenv import load_dotenv
from requests import RequestException

load_dotenv()

APP_DIR = Path(__file__).resolve().parent
STATE_FILE = Path(os.getenv("STATE_FILE", APP_DIR / "posted_videos.json"))
CHANNELS_FILE = Path(os.getenv("CHANNELS_FILE", APP_DIR / "config" / "channels.json"))
LOG_FILE = Path(os.getenv("LOG_FILE", APP_DIR / "ai_media_bot.log"))

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "").strip()
DISCORD_CHANNEL_ID_RAW = os.getenv("DISCORD_CHANNEL_ID", os.getenv("CHANNEL_ID", "")).strip()
DISCORD_GUILD_ID_RAW = os.getenv("DISCORD_GUILD_ID", "").strip()
CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "900"))
MAX_POSTS_PER_CHECK = int(os.getenv("MAX_POSTS_PER_CHECK", "10"))
POST_ON_FIRST_RUN = os.getenv("POST_ON_FIRST_RUN", "false").strip().lower() in {"1", "true", "yes", "on"}
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "20"))

YOUTUBE_FEED_URL = "https://www.youtube.com/feeds/videos.xml"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.FileHandler(LOG_FILE), logging.StreamHandler()],
)


@dataclass(frozen=True)
class YouTubeChannel:
    channel_id: str
    name: str | None = None


@dataclass(frozen=True)
class YouTubeVideo:
    video_id: str
    title: str
    url: str
    channel_id: str
    channel_name: str
    published: str | None = None


def split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def normalize_channel_id(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        marker = "/channel/"
        if marker in value:
            return value.split(marker, 1)[1].split("/", 1)[0].split("?", 1)[0]
    return value


def channels_from_env() -> list[YouTubeChannel]:
    raw_ids = os.getenv("YOUTUBE_CHANNEL_IDS", "")
    raw_names = os.getenv("YOUTUBE_CHANNEL_NAMES", "")
    ids = [normalize_channel_id(item) for item in split_csv(raw_ids)]
    names = split_csv(raw_names)
    channels: list[YouTubeChannel] = []
    for index, channel_id in enumerate(ids):
        if not channel_id:
            continue
        name = names[index] if index < len(names) else None
        channels.append(YouTubeChannel(channel_id=channel_id, name=name))
    return channels


def channels_from_file(path: Path = CHANNELS_FILE) -> list[YouTubeChannel]:
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError(f"{path} must contain a JSON list")

    channels: list[YouTubeChannel] = []
    for item in data:
        if isinstance(item, str):
            channel_id = normalize_channel_id(item)
            name = None
        elif isinstance(item, dict):
            channel_id = normalize_channel_id(str(item.get("channel_id") or item.get("id") or item.get("url") or ""))
            name = item.get("name")
        else:
            raise ValueError(f"Invalid channel entry in {path}: {item!r}")
        if channel_id:
            channels.append(YouTubeChannel(channel_id=channel_id, name=name))
    return channels


def load_channels() -> list[YouTubeChannel]:
    seen: set[str] = set()
    channels: list[YouTubeChannel] = []
    for channel in [*channels_from_file(), *channels_from_env()]:
        if channel.channel_id in seen:
            continue
        seen.add(channel.channel_id)
        channels.append(channel)
    return channels


def load_state(path: Path = STATE_FILE) -> set[str]:
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        logging.error("State file is invalid JSON: %s", path)
        return set()
    if isinstance(data, list):
        return set(str(item) for item in data)
    if isinstance(data, dict):
        return set(str(item) for item in data.get("posted_video_ids", []))
    return set()


def save_state(posted_video_ids: Iterable[str], path: Path = STATE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "posted_video_ids": sorted(set(posted_video_ids)),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def fetch_channel_videos(channel: YouTubeChannel) -> list[YouTubeVideo]:
    url = f"{YOUTUBE_FEED_URL}?{urlencode({'channel_id': channel.channel_id})}"
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS, headers={"User-Agent": "ai-media-bot/0.1"})
    response.raise_for_status()

    parsed = feedparser.parse(response.text)
    if parsed.bozo:
        logging.warning("Feed parse warning for %s: %s", channel.channel_id, parsed.bozo_exception)

    fallback_channel_name = channel.name or parsed.feed.get("title") or channel.channel_id
    videos: list[YouTubeVideo] = []
    for entry in parsed.entries:
        video_id = entry.get("yt_videoid") or entry.get("id", "").split(":")[-1]
        if not video_id:
            continue
        videos.append(
            YouTubeVideo(
                video_id=video_id,
                title=entry.get("title", "Untitled video"),
                url=entry.get("link") or f"https://www.youtube.com/watch?v={video_id}",
                channel_id=channel.channel_id,
                channel_name=fallback_channel_name,
                published=entry.get("published"),
            )
        )
    return videos


def video_sort_key(video: YouTubeVideo) -> datetime:
    if not video.published:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = parsedate_to_datetime(video.published)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed
    except (TypeError, ValueError):
        try:
            return datetime.fromisoformat(video.published.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return datetime.min.replace(tzinfo=timezone.utc)


def fetch_all_videos(channels: list[YouTubeChannel]) -> list[YouTubeVideo]:
    videos: list[YouTubeVideo] = []
    for channel in channels:
        try:
            channel_videos = fetch_channel_videos(channel)
            logging.info("Fetched %s videos from %s", len(channel_videos), channel.name or channel.channel_id)
            videos.extend(channel_videos)
        except RequestException as exc:
            logging.warning("Failed to fetch YouTube feed for %s: %s", channel.channel_id, exc)
        except Exception as exc:
            logging.error("Unexpected error fetching %s: %s\n%s", channel.channel_id, exc, traceback.format_exc())
    return sorted(videos, key=video_sort_key, reverse=True)


def format_video_message(video: YouTubeVideo) -> str:
    published = f"\nPublished: {video.published}" if video.published else ""
    return f"📺 **{video.channel_name}** uploaded:\n{video.title}{published}\n{video.url}"


intents = discord.Intents.default()
client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)
posted_video_ids: set[str] = set()
configured_channels: list[YouTubeChannel] = []


def get_discord_channel_id() -> int:
    if not DISCORD_CHANNEL_ID_RAW:
        raise ValueError("DISCORD_CHANNEL_ID is missing")
    return int(DISCORD_CHANNEL_ID_RAW)


def get_discord_guild_id() -> int | None:
    if not DISCORD_GUILD_ID_RAW:
        return None
    return int(DISCORD_GUILD_ID_RAW)


async def post_new_videos(manual: bool = False) -> tuple[int, int]:
    global posted_video_ids
    videos = fetch_all_videos(configured_channels)
    if not videos:
        logging.info("No videos fetched.")
        return 0, 0

    new_videos = [video for video in videos if video.video_id not in posted_video_ids]
    if not posted_video_ids and not POST_ON_FIRST_RUN and not manual:
        posted_video_ids.update(video.video_id for video in videos)
        save_state(posted_video_ids)
        logging.info("First run: seeded %s existing videos without posting.", len(videos))
        return 0, len(videos)

    if not new_videos:
        logging.info("No new videos found.")
        return 0, len(videos)

    new_videos = list(reversed(new_videos))[:MAX_POSTS_PER_CHECK]
    channel = client.get_channel(get_discord_channel_id())
    if channel is None:
        logging.error("Could not find Discord channel %s", DISCORD_CHANNEL_ID_RAW)
        return 0, len(videos)

    posted_count = 0
    for video in new_videos:
        try:
            await channel.send(format_video_message(video))
            posted_video_ids.add(video.video_id)
            posted_count += 1
            logging.info("Posted video: %s (%s)", video.title, video.url)
            await asyncio.sleep(1)
        except discord.errors.Forbidden:
            logging.error("Missing permission to send messages to Discord channel %s", DISCORD_CHANNEL_ID_RAW)
            break
        except discord.errors.HTTPException as exc:
            logging.error("Discord HTTP error posting %s: %s", video.video_id, exc)
            continue

    if posted_count:
        save_state(posted_video_ids)
    return posted_count, len(videos)


@client.event
async def on_ready() -> None:
    global posted_video_ids, configured_channels
    posted_video_ids = load_state()
    configured_channels = load_channels()
    logging.info("Logged in as %s (%s)", client.user, client.user.id if client.user else "unknown")
    logging.info("Loaded %s posted video IDs and %s YouTube channels", len(posted_video_ids), len(configured_channels))

    guild_id = get_discord_guild_id()
    if guild_id:
        guild = discord.Object(id=guild_id)
        tree.copy_global_to(guild=guild)
        synced = await tree.sync(guild=guild)
        logging.info("Synced %s slash commands to guild %s", len(synced), guild_id)
    else:
        synced = await tree.sync()
        logging.info("Synced %s global slash commands", len(synced))

    if not media_check_task.is_running():
        media_check_task.start()


@tasks.loop(seconds=CHECK_INTERVAL_SECONDS)
async def media_check_task() -> None:
    try:
        await post_new_videos(manual=False)
    except Exception as exc:
        logging.error("Error in media check loop: %s\n%s", exc, traceback.format_exc())


@media_check_task.before_loop
async def before_media_check() -> None:
    await client.wait_until_ready()


async def is_application_owner(user: discord.abc.User) -> bool:
    app_info = await client.application_info()
    if app_info.owner and app_info.owner.id == user.id:
        return True
    if app_info.team:
        return any(member.id == user.id for member in app_info.team.members)
    return False


@tree.command(name="testmedia", description="Check whether AI Media Bot is running.")
async def test_media(interaction: discord.Interaction) -> None:
    await interaction.response.send_message(
        f"AI Media Bot is running. Tracking {len(configured_channels)} YouTube channels.",
        ephemeral=True,
    )


@tree.command(name="mediachannels", description="List the YouTube channels AI Media Bot tracks.")
async def media_channels(interaction: discord.Interaction) -> None:
    if not configured_channels:
        await interaction.response.send_message("No YouTube channels configured.", ephemeral=True)
        return
    lines = [f"- {channel.name or channel.channel_id} (`{channel.channel_id}`)" for channel in configured_channels]
    await interaction.response.send_message("Tracked YouTube channels:\n" + "\n".join(lines[:25]), ephemeral=True)


@tree.command(name="checkmedia", description="Owner-only: check YouTube feeds now and post new videos.")
async def check_media(interaction: discord.Interaction) -> None:
    if not await is_application_owner(interaction.user):
        await interaction.response.send_message("Owner-only command.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    posted_count, seen_count = await post_new_videos(manual=True)
    await interaction.followup.send(f"Done. Posted {posted_count} new videos. Saw {seen_count} videos across configured feeds.", ephemeral=True)


@tree.command(name="latestmedia", description="Post the latest video from the configured YouTube feeds.")
async def latest_media(interaction: discord.Interaction) -> None:
    await interaction.response.defer()
    videos = fetch_all_videos(configured_channels)
    if not videos:
        await interaction.followup.send("No videos found.")
        return
    await interaction.followup.send(format_video_message(videos[0]))


def validate_config() -> None:
    if not DISCORD_TOKEN:
        raise ValueError("DISCORD_TOKEN is missing")
    get_discord_channel_id()
    channels = load_channels()
    if not channels:
        raise ValueError("No YouTube channels configured. Use config/channels.json or YOUTUBE_CHANNEL_IDS.")


if __name__ == "__main__":
    try:
        validate_config()
        logging.info("Starting AI Media Bot...")
        client.run(DISCORD_TOKEN, log_handler=None)
    except Exception as exc:
        logging.critical("Bot failed to start: %s\n%s", exc, traceback.format_exc())
        raise
