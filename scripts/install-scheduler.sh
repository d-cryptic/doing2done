#!/usr/bin/env bash
# Install the doing2done LaunchAgent (runs every 30 min).
set -euo pipefail
SRC="/Users/barun/Developers/personal/doing2done/scripts/com.doing2done.sync.plist"
DST="$HOME/Library/LaunchAgents/com.doing2done.sync.plist"
cp "$SRC" "$DST"
launchctl unload "$DST" 2>/dev/null || true
launchctl load "$DST"
echo "Loaded com.doing2done.sync (every 30 min)."
echo "Run once now:  launchctl start com.doing2done.sync"
echo "Tail logs:     tail -f /Users/barun/Developers/personal/doing2done/data/sync.log"
echo "Stop/remove:   launchctl unload $DST && rm $DST"
