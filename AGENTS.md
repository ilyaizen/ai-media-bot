# ai-media-bot

Use the files in this repo as the source of truth for runtime behavior and deployment.

## Setup checklist

- Create `.env` with `DISCORD_TOKEN` and `DISCORD_CHANNEL_ID`.
- Populate `config/channels.json` or set `YOUTUBE_CHANNEL_IDS` in `.env`.
- Make sure `posted_videos.json` is writable by the service user.

## Things to keep current

- `config/channels.json` when the tracked channel list changes.
- `posted_videos.json` only when you intentionally want to reseed or repost.

## Commands

- Local run: `./venv/bin/python main.py`
- Service health: `systemctl status aimediabot.service`
- Logs: `journalctl -u aimediabot.service -f`
- Slash command sync happens in `main.py`; restart the service after command changes.
