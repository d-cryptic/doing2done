#!/usr/bin/env bash
# doing2done scheduled sync: ingest -> deploy (if changed) -> best-effort git push.
set -uo pipefail
export PATH="/Users/barun/.bun/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"

REPO="/Users/barun/Developers/personal/doing2done"
VAULT="/Users/barun/Developers/personal/doing2done-vault"
GIT_ID=(-c user.email="barun.debnath2001@gmail.com" -c user.name="Barun Debnath")

notify() { uv run python -c "from doing2done.notify import notify; notify(\"$1\")" 2>/dev/null || true; }
echo "=== $(date -u +%Y-%m-%dT%H:%M:%SZ) doing2done sync ==="
cd "$REPO" || exit 1

# 1) ingest (writes todos to TickTick + notes/diagrams to the vault; reconciles deletes)
uv run d2d ingest --apply || notify "scheduled ingest failed"

# 1b) daily brief with rollover (idempotent per day: skips if the note exists)
uv run d2d daily --target both || notify "daily brief failed"

# 2) publish only if the vault changed
cd "$VAULT" || exit 1
if [[ -n "$(git status --porcelain)" ]]; then
  echo "vault changed -> deploy + push"
  ( cd "$REPO" && uv run d2d deploy-site ) || notify "deploy failed"
  git add -A
  git "${GIT_ID[@]}" commit -m "content: scheduled sync $(date -u +%Y-%m-%dT%H:%MZ)" || true
  git push || true   # best-effort; deploy already published the site
else
  echo "no vault changes"
fi
echo "=== done ==="
