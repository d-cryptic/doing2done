# doing2done

> **macOS only** · Turn handwritten **Apple Notes** into **smart TickTick todos** + a private,
> searchable **note vault**. Ink in, done out.
>
> **New here? → [SETUP.md](SETUP.md)** for the full first-run guide. TL;DR: `uv run d2d init`.
>
> **Capture/ask from anywhere → [INTERFACES.md](INTERFACES.md)** (Apple Shortcuts, email, WhatsApp, web).

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
uv run d2d daily                                          # daily brief + rollover -> Apple Notes + vault
uv run d2d tags                                           # regenerate the vault tag index
uv run d2d weekly                                         # LLM weekly review digest
uv run d2d relate                                         # backlinks/related-notes (TF-IDF + tags)
uv run d2d ask "what did I decide about X?"               # RAG over your notes
uv run d2d capture                                        # pull Telegram messages -> todos/notes
uv run d2d dedup                                          # near-duplicate notes report
uv run d2d enrich-links                                   # fetch + summarize URLs in notes
uv run d2d insights                                       # LLM themes/patterns report
uv run d2d analytics / timeline / graph                   # dashboards + views
uv run d2d eval                                           # extraction quality harness
```

## Eval harness

`d2d eval` runs the classifier over golden cases in `evals/cases.py` and fails on
regressions — missing todos, **hallucinated** todos, bad time parsing, missing subtasks.
It caught the class of bug where handwritten notes invented todos from the title.
Add a case whenever you fix an extraction bug. (Needs an LLM key, so it runs locally,
not in CI — add `LLM_API_KEY` as a repo secret to enable it there.)


## Features

- **Ingest** — reads Apple Notes directly from NoteStore (FDA-only), classifies via LLM.
- **Enrichment** — every note gets a title, tags, a TL;DR, and extracted links.
- **Diagrams** — full-resolution handwriting capture + vision caption (text vs diagram, meaning/goal).
- **TickTick** — todos smart-routed into your lists; reconciliation completes removed/deleted items.
- **Daily note + rollover** — `d2d daily` builds a templated brief (focus + rolled-over overdue) into Apple Notes and the vault.
- **Vault** — VitePress site with search, tag index, and daily notes, gated by Cloudflare Access.
- **Related notes / graph** — TF-IDF + shared-tag backlinks injected per note (semantic discovery, no embeddings API).
- **Two-way reflection** — daily note's Done section shows recently-completed tasks; TickTick completions drop from the rollover automatically.
- **Scheduler** — launchd runs ingest + daily + relate + deploy every 30 min (FDA-only, no Automation for reads).

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

## Todo providers (pluggable)

The todo layer is provider-agnostic — pick your app via `TODO_PROVIDER`:

| Provider | `TODO_PROVIDER` | Notes |
|----------|-----------------|-------|
| **TickTick** | `ticktick` | default; OAuth + smart lists |
| **Apple Reminders** | `reminders` | macOS-native, no account (needs Automation permission) |
| **Markdown file** | `markdown` | zero-dependency, git-friendly `todos.md` — works anywhere |

Adding another backend (Todoist, CalDAV, Things…) is one file implementing the
`TodoProvider` protocol in `src/doing2done/providers/`.
