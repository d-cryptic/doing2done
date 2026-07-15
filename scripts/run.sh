#!/usr/bin/env bash
# doing2done scheduled sync: ingest -> deploy (if changed) -> best-effort git push.
set -uo pipefail
export PATH="$HOME/.bun/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

REPO="$(cd "$(dirname "$0")/.." && pwd)"
VAULT="${DOING2DONE_VAULT:-$REPO/../doing2done-vault}"

notify() { uv run python -c "from doing2done.notify import notify; notify(\"$1\")" 2>/dev/null || true; }
echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) doing2done sync ==="
cd "$REPO" || exit 1

# 0) canary — catch silent failures (Notes access, token, worker, staleness)
uv run d2d health || true   # health notifies on its own

# 0b) pull any queued captures
uv run d2d capture || notify "capture failed"

# 1) ingest (writes todos to TickTick + notes/diagrams to the vault; reconciles deletes)
uv run d2d ingest --apply || notify "scheduled ingest failed"

# 1b) daily brief with rollover (idempotent per day: skips if the note exists)
uv run d2d daily --target both || notify "daily brief failed"
uv run d2d calendar --apply || true   # mirror due dates to Apple Calendar
uv run d2d analytics || true
uv run d2d librarian --apply || true   # garden weak metadata (no-op when tidy)

# 1c) vault hygiene — all local (no LLM), so it's cheap to run every sync.
# A retitle changes a note's stem, which strands the old file and every link
# pointing at it; prune archives the strays and relate rewrites the links.
uv run d2d prune --apply || true
uv run d2d retag --apply || true
uv run d2d relate || true
uv run d2d tags || true
uv run d2d dedup || true
uv run d2d timeline || true
uv run d2d graph || true
uv run d2d home || true   # front page is built from the notes, so it must follow them
# The dashboards emit raw HTML anchors, which VitePress's dead-link check ignores.
uv run d2d linkcheck || notify "vault has broken internal links" 
uv run d2d backup || notify "state backup failed"   # dedup map is irreplaceable
uv run d2d push || notify "edge push failed"

# 2) publish only if the vault changed
cd "$VAULT" || exit 1
if [[ -n "$(git status --porcelain)" ]]; then
  echo "vault changed -> deploy + push"
  ( cd "$REPO" && uv run d2d deploy-site ) || notify "deploy failed"
  git add -A
  git commit -m "content: scheduled sync $(date -u +%Y-%m-%dT%H:%MZ)" || true
  git push || true   # best-effort; deploy already published the site
else
  echo "no vault changes"
fi
echo "=== done ==="
