#!/usr/bin/env bash
# Install the doing2done LaunchAgent (every 30 min), paths derived from this repo.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
mkdir -p "$HOME/Library/LaunchAgents"

install_job() {  # install_job <label> <description>
  local dst="$HOME/Library/LaunchAgents/$1.plist"
  sed "s#__REPO__#$REPO#g" "$REPO/scripts/$1.plist.tmpl" > "$dst"
  launchctl unload "$dst" 2>/dev/null || true
  launchctl load "$dst"
  echo "Loaded $1 ($2)"
}

install_job com.doing2done.sync    "every 30 min"
install_job com.doing2done.digest  "Sundays 18:00 — weekly review to Telegram"
install_job com.doing2done.surface "Wednesdays 09:00 — stale-work nudge to Telegram"

echo "Logs: $REPO/data/sync.log, $REPO/data/push.log"
echo "Run now: launchctl start com.doing2done.sync"
