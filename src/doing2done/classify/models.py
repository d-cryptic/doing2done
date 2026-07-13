"""Structured output contract for the classifier."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Todo(BaseModel):
    title: str
    due_date: str | None = Field(None, description="ISO 8601, e.g. 2026-07-15T09:00:00+0000")
    priority: str = Field("none", description="none|low|medium|high")
    project: str | None = Field(None, description="optional list/project hint")


class NoteResult(BaseModel):
    title: str = "Untitled"
    date: str | None = None
    tags: list[str] = Field(default_factory=list)
    todos: list[Todo] = Field(default_factory=list)
    markdown: str = Field("", description="clean markdown body for the note vault")
    summary: str = Field("", description="one-line TL;DR of the note")
    links: list[str] = Field(default_factory=list, description="URLs found in the note")
    is_todo_only: bool = False

    @field_validator("title", mode="before")
    @classmethod
    def _coerce_title(cls, v: object) -> str:
        return str(v) if v else "Untitled"

    @field_validator("tags", "todos", "links", mode="before")
    @classmethod
    def _none_to_list(cls, v: object) -> object:
        return v or []
