#!/usr/bin/env bash
set -euo pipefail

APP_DIR="/srv/apps/ai-media-bot"
ENV_FILE="$APP_DIR/.env"
CHANNELS_FILE="$APP_DIR/config/channels.json"
STATE_FILE="$APP_DIR/posted_videos.json"

if [[ ! -r "$ENV_FILE" ]]; then
  echo "Missing readable $ENV_FILE" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a

if [[ -z "${DISCORD_TOKEN:-}" ]]; then
  echo "DISCORD_TOKEN is missing in $ENV_FILE" >&2
  exit 1
fi

DISCORD_CHANNEL_ID="${DISCORD_CHANNEL_ID:-${CHANNEL_ID:-}}"
if [[ -z "$DISCORD_CHANNEL_ID" ]]; then
  echo "DISCORD_CHANNEL_ID is missing in $ENV_FILE" >&2
  exit 1
fi

if ! [[ "$DISCORD_CHANNEL_ID" =~ ^[0-9]+$ ]]; then
  echo "DISCORD_CHANNEL_ID must be numeric" >&2
  exit 1
fi

if [[ -z "${YOUTUBE_CHANNEL_IDS:-}" ]]; then
  if [[ ! -s "$CHANNELS_FILE" ]] || [[ "$(tr -d '[:space:]' < "$CHANNELS_FILE")" == "[]" ]]; then
    echo "No YouTube channels configured. Set YOUTUBE_CHANNEL_IDS or populate $CHANNELS_FILE" >&2
    exit 1
  fi
fi

if [[ ! -e "$STATE_FILE" ]]; then
  echo '{"posted_video_ids": []}' > "$STATE_FILE"
fi

if [[ ! -w "$STATE_FILE" ]]; then
  echo "$STATE_FILE is not writable by service user" >&2
  exit 1
fi

exit 0
