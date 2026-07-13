"""doing2done MCP server — exposes capture / ask / todos as tools for any agent.

Used by Hermes Agent (WhatsApp), Claude Desktop, Cursor, etc.:
  hermes mcp add doing2done --command "uv run d2d-mcp"
"""
from __future__ import annotations

import datetime as dt

import httpx

from .config import get_settings
from .providers import build_provider
from .providers.base import TaskDraft
from .state import State
from .todo import TodoService

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as e:  # pragma: no cover
    raise SystemExit("MCP SDK missing — install with: uv sync --extra mcp") from e

mcp = FastMCP("doing2done")


def _svc() -> TodoService | None:
    s = get_settings()
    state = State(s.state_db)
    prov = build_provider(s, state)
    return TodoService(prov, state, s.ticktick_default_project_id) if prov else None


@mcp.tool()
def ask_notes(query: str) -> str:
    """Semantic search over the user's private note vault. Returns the most relevant notes."""
    s = get_settings()
    if not s.worker_url or not s.ingest_token:
        return "Edge search not configured (set WORKER_URL + INGEST_TOKEN)."
    r = httpx.get(
        f"{s.worker_url}/ask", params={"q": query},
        headers={"Authorization": f"Bearer {s.ingest_token}"}, timeout=30,
    )
    r.raise_for_status()
    hits = r.json().get("hits", [])
    if not hits:
        return "No matching notes."
    return "Relevant notes:\n" + "\n".join(
        f"- {h.get('title')} (score {h.get('score')})" for h in hits
    )


@mcp.tool()
def capture(text: str) -> str:
    """Capture a quick thought; it becomes todos + a note on the next sync."""
    s = get_settings()
    if not s.worker_url or not s.ingest_token:
        return "Capture endpoint not configured."
    r = httpx.post(
        f"{s.worker_url}/capture", json={"source": "mcp", "text": text},
        headers={"Authorization": f"Bearer {s.ingest_token}"}, timeout=30,
    )
    r.raise_for_status()
    return "Captured ✅ (will sync into todos/notes)."


@mcp.tool()
def add_todo(title: str, due_date: str = "", priority: str = "none", project: str = "") -> str:
    """Add a todo to the user's configured app (TickTick/Reminders/Markdown)."""
    svc = _svc()
    if svc is None:
        return "No todo provider configured."
    try:
        svc.load_projects()
        svc.upsert(
            f"mcp:{dt.datetime.now().isoformat()}",
            TaskDraft(
                title=title, due_date=due_date or None, priority=priority,
                project_id=svc.resolve_pid(project or None),
            ),
        )
        return f"Added: {title}"
    finally:
        svc.close()


@mcp.tool()
def daily_brief() -> str:
    """Today's focus + rolled-over overdue tasks."""
    from . import daily as daily_mod

    svc = _svc()
    if svc is None:
        return "No todo provider configured."
    try:
        _title, md = daily_mod.build_brief(svc, state=State(get_settings().state_db))
        return md
    finally:
        svc.close()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
