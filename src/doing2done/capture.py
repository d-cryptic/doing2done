"""Pull queued captures (Shortcuts/email/WhatsApp) from the edge Worker and process them.

Channel-neutral: every capture channel lands in the Worker's `captures` queue; this
classifies each into todos (via the configured provider) + notes, then acks.
"""
from __future__ import annotations

import httpx

from .classify.classifier import classify_note
from .config import Settings
from .providers.base import TaskDraft
from .state import State
from .todo import TodoService
from .vault import write_note


def process_captures(settings: Settings, state: State, svc: TodoService | None) -> int:
    """Fetch pending captures from the Worker, route them, ack. Returns count."""
    if not settings.worker_url or not settings.ingest_token:
        return 0
    headers = {"Authorization": f"Bearer {settings.ingest_token}"}
    r = httpx.get(f"{settings.worker_url}/captures/pending", headers=headers, timeout=30)
    r.raise_for_status()
    caps = r.json().get("captures", [])
    if not caps:
        return 0

    projects = None
    if svc is not None:
        svc.load_projects()
        projects = svc.project_names

    done: list[str] = []
    for c in caps:
        note_id = f"capture:{c['id']}"
        try:
            result = classify_note(
                c["text"], provider=settings.llm_provider, api_key=settings.llm_api_key,
                model=settings.llm_model, base_url=settings.llm_base_url, projects=projects,
            )
        except Exception:
            done.append(c["id"])  # unparseable capture: ack so it doesn't loop forever
            continue
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
        done.append(c["id"])

    httpx.post(
        f"{settings.worker_url}/captures/ack", json={"ids": done}, headers=headers, timeout=30
    )
    return len(done)
