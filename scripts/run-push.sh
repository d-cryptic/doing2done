#!/usr/bin/env bash
# Scheduled push to Telegram: run-push.sh digest|surface
# Silent by design — `d2d digest`/`surface` print nothing and send nothing when
# there's genuinely nothing to say, so an empty week doesn't buzz your phone.
set -uo pipefail
export PATH="$HOME/.bun/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"
REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO" || exit 1

KIND="${1:-digest}"
echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) push: $KIND ==="
case "$KIND" in
  digest)  uv run d2d digest --send ;;
  surface) uv run d2d surface --send ;;
  *) echo "usage: run-push.sh digest|surface" >&2; exit 2 ;;
esac
