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
  digest)
    # The vault's LLM reports cost a call each, so they ride the weekly job rather
    # than the 30-minute sync. Insights was regenerating only when run by hand.
    uv run d2d insights || true
    uv run d2d weekly || true
    ( cd "$REPO" && uv run d2d deploy-site ) || true
    uv run d2d digest --send
    ;;
  surface) uv run d2d surface --send ;;
  *) echo "usage: run-push.sh digest|surface" >&2; exit 2 ;;
esac
