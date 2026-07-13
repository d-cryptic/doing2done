"""Forward-to-capture: poll Telegram for messages, turn them into todos/notes."""
from __future__ import annotations

import os
import re

import httpx

from .classify.classifier import classify_note
from .config import Settings
from .providers.base import TaskDraft
from .state import State
from .todo import TodoService
from .vault import write_note


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def poll_telegram(settings: Settings, state: State, svc: TodoService | None) -> int:
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

    projects = None
    if svc is not None:
        svc.load_projects()
        projects = svc.project_names

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
        if svc is not None:
            for todo in result.todos:
                svc.upsert(
                    note_id,
                    TaskDraft(
                        title=todo.title, due_date=todo.due_date, priority=todo.priority,
                        project_id=svc.resolve_pid(todo.project), items=todo.items,
                    ),
                )
        if not result.is_todo_only and result.markdown.strip():
            write_note(result, settings.vault_notes_dir, note_id=note_id)
        handled += 1
    state.set_kv("tg_offset", str(offset))
    return handled
