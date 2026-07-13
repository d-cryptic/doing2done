"""Provider-agnostic todo orchestration: dedup, routing, reconciliation."""
from __future__ import annotations

import re

from .providers.base import TaskDraft, TodoProvider
from .state import State


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


class TodoService:
    """Wraps any TodoProvider with dedup (via State), routing, and reconciliation."""

    def __init__(self, provider: TodoProvider, state: State, default_project: str = "") -> None:
        self.p = provider
        self.state = state
        self.default_project = default_project or ""
        self._name2id: dict[str, str] = {}
        self._norm2id: dict[str, str] = {}
        self._names: list[str] | None = None
        self._pid_cache: dict[str, str] = {}
        self._pid_built = False

    def load_projects(self) -> None:
        for pr in self.p.list_projects():
            self._name2id[pr.name] = pr.id
            self._norm2id[_norm(pr.name)] = pr.id
        self._names = list(self._name2id)

    @property
    def project_names(self) -> list[str] | None:
        return self._names

    def resolve_pid(self, hint: str | None) -> str | None:
        default = self.default_project or None
        if not hint:
            return default
        if hint in self._name2id:
            return self._name2id[hint]
        n = _norm(hint)
        if n in self._norm2id:
            return self._norm2id[n]
        for k, v in self._norm2id.items():
            if n and (n in k or k in n):
                return v
        return default

    def upsert(self, note_id: str, draft: TaskDraft) -> str:
        existing = self.state.get_task(note_id, draft.title)
        if existing:
            if existing["completed"]:
                return existing["task_id"]
            self.p.update_task(existing["task_id"], draft)
            return existing["task_id"]
        created = self.p.create_task(draft)
        self.state.remember_task(note_id, draft.title, created.id, created.project_id)
        return created.id

    def resolve_task_pid(self, task_id: str, stored_pid: str | None) -> str | None:
        if stored_pid:
            return stored_pid
        if not self._pid_built:
            self._pid_built = True
            for pid in set(self._name2id.values()):
                try:
                    for t in self.p.open_tasks(pid):
                        self._pid_cache[t.id] = pid
                except Exception:
                    pass
        return self._pid_cache.get(task_id)

    def complete(self, project_id: str | None, task_id: str) -> None:
        self.p.complete_task(project_id, task_id)

    def open_with_project(self) -> list[tuple]:
        """[(Task, project_name)] across all projects — for daily/analytics."""
        out = []
        for pr in self.p.list_projects():
            try:
                for t in self.p.open_tasks(pr.id):
                    out.append((t, pr.name))
            except Exception:
                pass
        return out

    def close(self) -> None:
        self.p.close()
