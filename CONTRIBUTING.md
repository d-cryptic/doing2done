# Contributing

Thanks for your interest! doing2done is a macOS-only personal-automation tool.

## Dev setup
```bash
uv sync --extra dev
uv run ruff check src/
uv run pytest -q
```

## Ground rules
- Keep it macOS-focused for the Apple Notes reader; other platforms can contribute
  alternative capture sources (Telegram/email/WhatsApp) which are platform-neutral.
- No secrets in commits. Config comes from `.env` (or `op://` 1Password refs).
- `ruff` + `pytest` must pass (CI enforces).
- One concern per PR; add tests for new logic.
