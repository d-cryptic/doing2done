# Setup

> **Requires macOS** — doing2done reads Apple Notes from the local `NoteStore.sqlite`.
> Capture channels (Telegram/email/WhatsApp) and the Cloudflare edge are platform-neutral,
> but the Apple Notes reader is macOS-only.

## Prerequisites
- macOS with Apple Notes (iCloud-synced)
- [uv](https://docs.astral.sh/uv/) . Node 20+ . [wrangler](https://developers.cloudflare.com/workers/wrangler/)
- Accounts: **TickTick**, **OpenRouter** (or any OpenAI-compatible LLM), **Cloudflare**
- Optional: [1Password CLI](https://developer.1password.com/docs/cli/) (`op`) for secrets

## 1. Bootstrap
```bash
git clone https://github.com/d-cryptic/doing2done && cd doing2done
uv sync --extra ocr --extra dev
uv run d2d init        # scaffolds ../<vault>, the env file, worker/wrangler.toml
```

## 2. Fill the env file
- **TickTick** — register an app at https://developer.ticktick.com/manage,
  redirect URI `http://localhost:8080/callback`, giving `TICKTICK_CLIENT_ID` / `_SECRET`.
- **LLM** — `LLM_API_KEY` (OpenRouter key; default model `google/gemini-2.5-flash`).
- **Cloudflare** — `CF_ADMIN_API_TOKEN` (Pages + Access edit), `CF_ACCOUNT_ID`,
  `CF_ACCESS_ALLOWED_EMAIL`.
- Any value may be a 1Password `op://...` reference instead of a literal.

## 3. Provision Cloudflare (once)
```bash
cd worker
wrangler d1 create doing2done
wrangler r2 bucket create doing2done-assets
wrangler vectorize create doing2done-notes --dimensions=768 --metric=cosine
# put the printed D1 database_id into worker/wrangler.toml, then:
echo "$(openssl rand -hex 24)" | wrangler secret put INGEST_TOKEN
wrangler deploy
```
Add `WORKER_URL` + `INGEST_TOKEN` to your env file.

## 4. macOS permission
System Settings -> Privacy & Security -> **Full Disk Access** -> add `/bin/bash`
(so the scheduler can read `NoteStore.sqlite`).

## 5. First run
```bash
uv run d2d auth            # TickTick OAuth (browser)
uv run d2d cf-check        # verify the Cloudflare token
uv run d2d ingest          # dry-run over your notes
uv run d2d ingest --apply  # sync todos + build the vault
uv run d2d deploy-site     # publish
uv run d2d gate-site --domain <project>.pages.dev
```

## 6. Automate
```bash
bash scripts/install-scheduler.sh   # launchd, every 30 min
```

See the [README](README.md) for the full command reference.
