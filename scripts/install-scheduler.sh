#!/usr/bin/env bash
# Install the doing2done LaunchAgent (every 30 min), paths derived from this repo.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
DST="$HOME/Library/LaunchAgents/com.doing2done.sync.plist"
mkdir -p "$HOME/Library/LaunchAgents"
sed "s#__REPO__#$REPO#g" "$REPO/scripts/com.doing2done.sync.plist.tmpl" > "$DST"
launchctl unload "$DST" 2>/dev/null || true
launchctl load "$DST"
echo "Loaded com.doing2done.sync (every 30 min). Logs: $REPO/data/sync.log"
echo "Run now: launchctl start com.doing2done.sync"
