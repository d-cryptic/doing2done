"""Todo provider factory — selects a backend from config."""
from __future__ import annotations

from ..config import Settings
from ..state import State
from .base import Project, Task, TaskDraft, TodoProvider

__all__ = ["Project", "Task", "TaskDraft", "TodoProvider", "build_provider"]


def build_provider(settings: Settings, state: State) -> TodoProvider | None:
    """Construct the configured provider (handles TickTick auth + refresh)."""
    kind = settings.todo_provider
    if kind == "markdown":
        from .markdown import MarkdownProvider

        path = settings.todo_file or f"{settings.vault_dir}/todos.md"
        return MarkdownProvider(path)
    if kind == "reminders":
        from .reminders import RemindersProvider

        return RemindersProvider()

    # default: ticktick (with token refresh on 401)
    import httpx

    from ..ticktick import oauth
    from .ticktick import TickTickProvider

    tok = oauth.load_token(settings.ticktick_token_path)
    if not tok:
        return None
    prov = TickTickProvider(tok["access_token"])
    try:
        prov.list_projects()
        return prov
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 401:
            new = oauth.refresh(
                settings.ticktick_client_id, settings.ticktick_client_secret,
                settings.ticktick_token_path,
            )
            if new:
                prov.close()
                return TickTickProvider(new["access_token"])
        raise
