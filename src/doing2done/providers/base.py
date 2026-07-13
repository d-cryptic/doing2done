"""Provider-agnostic todo interface. Any todo/reminder backend implements this."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# normalized priority scale (TickTick-compatible): 0 none · 1 low · 3 medium · 5 high
PRIORITY = {"none": 0, "low": 1, "medium": 3, "high": 5}


@dataclass(frozen=True)
class Project:
    id: str
    name: str


@dataclass
class TaskDraft:
    title: str
    content: str | None = None
    due_date: str | None = None            # ISO 8601, optional time
    priority: str = "none"                 # none|low|medium|high
    project_id: str | None = None
    items: list[str] = field(default_factory=list)   # subtasks


@dataclass
class Task:
    id: str
    title: str
    project_id: str | None = None
    priority: int = 0
    due_date: str | None = None
    completed: bool = False


@runtime_checkable
class TodoProvider(Protocol):
    """Minimal surface every backend must implement."""

    name: str

    def list_projects(self) -> list[Project]: ...
    def open_tasks(self, project_id: str) -> list[Task]: ...
    def create_task(self, draft: TaskDraft) -> Task: ...
    def update_task(self, task_id: str, draft: TaskDraft) -> None: ...
    def complete_task(self, project_id: str | None, task_id: str) -> None: ...

    def close(self) -> None: ...
