"""Structured output contract for the classifier."""
from __future__ import annotations

from pydantic import BaseModel, Field


class Todo(BaseModel):
    title: str
    due_date: str | None = Field(None, description="ISO 8601, e.g. 2026-07-15T09:00:00+0000")
    priority: str = Field("none", description="none|low|medium|high")
    project: str | None = Field(None, description="optional list/project hint")


class NoteResult(BaseModel):
    title: str
    date: str | None = None
    tags: list[str] = Field(default_factory=list)
    todos: list[Todo] = Field(default_factory=list)
    markdown: str = Field("", description="clean markdown body for the note vault")
    is_todo_only: bool = False
