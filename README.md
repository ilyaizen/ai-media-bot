# ai-media-bot

Discord bot that watches a configurable list of YouTube channels and posts newly uploaded videos to one Discord channel.

It uses YouTube's public RSS feeds first, then falls back to scraping the channel page when needed. No YouTube API key is required.

## What it does

- Polls tracked YouTube channels every 15 minutes by default.
- Stores posted video IDs in `posted_videos.json`.
- Seeds existing videos on first run without spamming the server unless `POST_ON_FIRST_RUN=true`.
- Supports these slash commands:
  - `/testmedia` — health check
  - `/mediachannels` — list tracked channels
  - `/latestmedia` — show the latest fetched video
  - `/checkmedia` — owner-only manual check/post

## Setup

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
cp .env.example .env
cp config/channels.example.json config/channels.json
```

Edit `.env`:

```dotenv
DISCORD_TOKEN=your_discord_bot_token
DISCORD_CHANNEL_ID=123456789012345678
# Optional overrides:
# YOUTUBE_CHANNEL_IDS=UCxxxxxxxxxxxxxxxxxxxxxx,UCyyyyyyyyyyyyyyyyyyyyyy
# YOUTUBE_CHANNEL_NAMES=Channel One,Channel Two
# CHECK_INTERVAL_SECONDS=900
# MAX_POSTS_PER_CHECK=10
# POST_ON_FIRST_RUN=false
```

Then add the tracked channels either in `config/channels.json`:

```json
[
  {
    "name": "Two Minute Papers",
    "channel_id": "UCbfYPyITQ-7l4upoX8nvctg"
  }
]
```

or via `.env` using the comma-separated `YOUTUBE_CHANNEL_IDS` list.

## Run locally

```bash
./venv/bin/python main.py
```

## Discord setup

In the Discord Developer Portal:

1. Create a bot application.
2. Invite it with permission to read/send messages in the target channel.
3. Register the bot's slash commands in the target guild if you want them to appear quickly.
4. Put the target text channel ID in `DISCORD_CHANNEL_ID`.

## Operational notes

- `config/channels.json` is the unique tracked-channel list. Keep it under version control and commit it regularly whenever the tracked YouTube set changes.
- `posted_videos.json` is the bot's memory. Delete it only if you intentionally want to reseed/repost.
- `MAX_POSTS_PER_CHECK` is there to stop a backlog from dumping everything at once.
- If YouTube changes its page structure, the fallback scraper may need maintenance.

## Server deployment

```bash
sudo useradd --system --home /srv/apps/ai-media-bot --shell /usr/sbin/nologin aimediabot
sudo chown -R aimediabot:aimediabot /srv/apps/ai-media-bot
sudo chmod +x /srv/apps/ai-media-bot/scripts/preflight.sh
sudo -u aimediabot python3 -m venv /srv/apps/ai-media-bot/venv
sudo -u aimediabot /srv/apps/ai-media-bot/venv/bin/pip install -r /srv/apps/ai-media-bot/requirements.txt
sudo cp /srv/apps/ai-media-bot/deploy/aimediabot.service /etc/systemd/system/aimediabot.service
sudo systemctl daemon-reload
sudo systemctl enable --now aimediabot.service
sudo journalctl -u aimediabot.service -f
```
