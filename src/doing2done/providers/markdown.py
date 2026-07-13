"""Zero-dependency todo provider: a local Markdown checklist file (git-friendly)."""
from __future__ import annotations

import re
import uuid
from pathlib import Path

from .base import Project, Task, TaskDraft

_LINE = re.compile(r"^- \[( |x)\] (.*?)\s*<!--d2d:([0-9a-f]+)-->\s*$")


class MarkdownProvider:
    name = "markdown"

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        if not self.path.exists():
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text("# Todos\n\n## Inbox\n")

    def _read(self) -> str:
        return self.path.read_text()

    def list_projects(self) -> list[Project]:
        names = re.findall(r"^## (.+)$", self._read(), re.M)
        return [Project(id=n.strip(), name=n.strip()) for n in names] or [Project("Inbox", "Inbox")]

    def open_tasks(self, project_id: str) -> list[Task]:
        out, cur = [], None
        for line in self._read().splitlines():
            h = re.match(r"^## (.+)$", line)
            if h:
                cur = h.group(1).strip()
                continue
            m = _LINE.match(line)
            if m and m.group(1) == " " and cur == project_id:
                out.append(Task(id=m.group(3), title=m.group(2), project_id=cur))
        return out

    def create_task(self, draft: TaskDraft) -> Task:
        tid = uuid.uuid4().hex[:12]
        section = draft.project_id or "Inbox"
        text = self._read()
        entry = f"- [ ] {draft.title}"
        if draft.due_date:
            entry += f"  (due {draft.due_date.split('T')[0]})"
        entry += f"  <!--d2d:{tid}-->"
        if f"## {section}" not in text:
            text += f"\n## {section}\n"
        lines = text.splitlines()
        target = f"## {section}"
        idx = next((i for i, ln in enumerate(lines) if ln.strip() == target), len(lines) - 1)
        lines.insert(idx + 1, entry)
        for j, sub in enumerate(draft.items):
            lines.insert(idx + 2 + j, f"  - [ ] {sub}")
        self.path.write_text("\n".join(lines) + "\n")
        return Task(id=tid, title=draft.title, project_id=section)

    def update_task(self, task_id: str, draft: TaskDraft) -> None:
        lines = self._read().splitlines()
        for i, ln in enumerate(lines):
            m = _LINE.match(ln)
            if m and m.group(3) == task_id:
                lines[i] = f"- [ ] {draft.title} <!--d2d:{task_id}-->"
        self.path.write_text("\n".join(lines) + "\n")

    def complete_task(self, project_id: str | None, task_id: str) -> None:
        lines = self._read().splitlines()
        for i, ln in enumerate(lines):
            m = _LINE.match(ln)
            if m and m.group(3) == task_id:
                lines[i] = ln.replace("- [ ]", "- [x]", 1)
        self.path.write_text("\n".join(lines) + "\n")

    def close(self) -> None:
        pass
