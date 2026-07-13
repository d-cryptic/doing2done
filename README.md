# doing2done

Turn handwritten **Apple Notes** into **smart TickTick todos** + a private, hosted
**note vault**. Ink in, done out.

```
iPad (Apple Pencil) --iCloud--> Mac ingest ──┬─> TickTick (todos, auto-managed)
                                             └─> Markdown -> doing2done-vault (VitePress, Cloudflare Access)
```

## Setup

```bash
uv sync                 # core deps
uv sync --extra ocr     # + Apple Vision (on-device handwriting OCR)
cp .env.example .env    # fill in the blanks (see below)
```

Fill `.env`:
- **TickTick** — register an app at https://developer.ticktick.com/manage, set the
  redirect URI to `http://localhost:8080/callback`, paste `TICKTICK_CLIENT_ID` / `_SECRET`.
- **LLM** — a cheap model key (`LLM_API_KEY`, Gemini Flash by default).
- **Cloudflare** — `CF_ADMIN_API_TOKEN` (+ Access service token) — already provisioned.

## Commands

```bash
uv run d2d auth            # one-time TickTick OAuth (opens browser)
uv run d2d ticktick-check  # list your TickTick projects (verifies token)
uv run d2d cf-check        # verify the Cloudflare token can manage Pages
uv run d2d ingest          # DRY-RUN: show what would sync (no writes)
uv run d2d ingest --apply  # actually upsert todos + write vault markdown
uv run d2d gate-site --domain doing2done-vault.pages.dev   # Access: only your email
```

## Layout

```
src/doing2done/
  config.py            # typed settings from .env
  state.py             # SQLite dedup (note_id -> task_id) + watermark
  ticktick/            # OAuth + Open API client (upsert/complete)
  notes/               # export.py (JXA) + ocr.py (Apple Vision)
  classify/            # cheap-LLM -> {todos, markdown, title, date, tags}
  cloudflare/          # Pages project + Access policy via API
  vault.py             # write markdown into the VitePress vault
  pipeline.py          # orchestrates the ingest
  cli.py               # `d2d` entrypoint
```

See the build plan for the full architecture and phase breakdown.
