"""Forward-to-capture: poll Telegram for messages, turn them into todos/notes."""
from __future__ import annotations

import os
import re

import httpx

from .classify.classifier import classify_note
from .config import Settings
from .state import State
from .ticktick.client import TickTickClient
from .vault import write_note


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def poll_telegram(settings: Settings, state: State, tt: TickTickClient | None) -> int:
    """Process new Telegram messages into todos + notes. Returns count handled."""
    tok = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not tok:
        return 0
    offset = int(state.get_kv("tg_offset") or 0)
    r = httpx.get(
        f"https://api.telegram.org/bot{tok}/getUpdates",
        params={"offset": offset + 1, "timeout": 0},
        timeout=25,
    )
    updates = r.json().get("result", [])

    name2id: dict[str, str] = {}
    if tt is not None:
        for p in tt.projects():
            name2id[_norm(p["name"])] = p["id"]
    projects = None if tt is None else [p["name"] for p in tt.projects()]

    def pid(proj: str | None) -> str | None:
        if not proj:
            return settings.ticktick_default_project_id or None
        return name2id.get(_norm(proj), settings.ticktick_default_project_id or None)

    handled = 0
    for u in updates:
        offset = max(offset, u["update_id"])
        text = (u.get("message") or {}).get("text", "").strip()
        if not text:
            continue
        note_id = f"telegram:{u['update_id']}"
        result = classify_note(
            text,
            provider=settings.llm_provider,
            api_key=settings.llm_api_key,
            model=settings.llm_model,
            base_url=settings.llm_base_url,
            projects=projects,
        )
        if tt is not None:
            for todo in result.todos:
                tt.upsert_task(
                    note_id, todo.title, due_date=todo.due_date, priority=todo.priority,
                    project_id=pid(todo.project), items=todo.items,
                )
        if not result.is_todo_only and result.markdown.strip():
            write_note(result, settings.vault_notes_dir, note_id=note_id)
        handled += 1
    state.set_kv("tg_offset", str(offset))
    return handled
