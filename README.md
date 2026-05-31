# AI Media Discord Bot

Discord bot that watches a configured list of YouTube channels and posts newly uploaded videos to one Discord channel.

It uses YouTube's public RSS feeds, so no YouTube API key is needed.

## Behavior

- Polls YouTube channel feeds every 15 minutes by default.
- Stores posted video IDs in `posted_videos.json`.
- On first run, seeds existing feed videos without posting them, so it does not spam the server.
- Posts only new videos after that.
- Supports manual commands:
  - `!testmedia` — health check
  - `!mediachannels` — list tracked channels
  - `!latestmedia` — show latest fetched video
  - `!checkmedia` — owner-only manual check/post

## Local setup

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
```

Then add YouTube channels using either `config/channels.json`:

```json
[
  { "name": "Two Minute Papers", "channel_id": "UCbfYPyITQ-7l4upoX8nvctg" }
]
```

or `.env`:

```dotenv
YOUTUBE_CHANNEL_IDS=UCbfYPyITQ-7l4upoX8nvctg,UCXZCJLdBC09xxGZ6gcdrc6A
YOUTUBE_CHANNEL_NAMES=Two Minute Papers,Example Channel
```

Run:

```bash
./venv/bin/python main.py
```

## Discord setup notes

In the Discord Developer Portal:

1. Create a bot application.
2. Enable **Message Content Intent** if you want prefix commands like `!testmedia`.
3. Invite it with permission to read/send messages in the target channel.
4. Copy the target Discord channel ID into `DISCORD_CHANNEL_ID`.

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

## Safety knobs

- `POST_ON_FIRST_RUN=false` avoids dumping old videos into Discord on first boot.
- `MAX_POSTS_PER_CHECK=10` caps bursts if the bot was offline.
- Delete `posted_videos.json` only if you intentionally want to re-seed/repost depending on `POST_ON_FIRST_RUN`.
