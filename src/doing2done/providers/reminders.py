"""Apple Reminders provider (macOS, via osascript JXA). Needs Automation permission."""
from __future__ import annotations

import json
import subprocess

from .base import Project, Task, TaskDraft

# Reminders priority: 0 none, 1 high, 5 medium, 9 low (Apple's scale)
_PRIO = {"none": 0, "high": 1, "medium": 5, "low": 9}


def _jxa(script: str, *args: str) -> str:
    p = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", script, *args],
        capture_output=True, text=True, check=True,
    )
    return p.stdout.strip()


class RemindersProvider:
    name = "reminders"

    def list_projects(self) -> list[Project]:
        out = _jxa(
            "function run(){const R=Application('Reminders');"
            "return JSON.stringify(R.lists().map(l=>({id:l.id(),name:l.name()})));}"
        )
        return [Project(id=x["id"], name=x["name"]) for x in json.loads(out or "[]")]

    def open_tasks(self, project_id: str) -> list[Task]:
        out = _jxa(
            "function run(argv){const R=Application('Reminders');"
            "const l=R.lists.byId(argv[0]);"
            "return JSON.stringify(l.reminders().filter(r=>!r.completed())"
            ".map(r=>({id:r.id(),title:r.name()})));}",
            project_id,
        )
        return [Task(id=x["id"], title=x["title"], project_id=project_id)
                for x in json.loads(out or "[]")]

    def create_task(self, draft: TaskDraft) -> Task:
        out = _jxa(
            "function run(argv){const R=Application('Reminders');"
            "const [title,listName]=argv;"
            "let l; try{l=R.lists.byName(listName); l.name();}catch(e){l=R.defaultList;}"
            "const r=R.Reminder({name:title}); l.reminders.push(r);"
            "return JSON.stringify({id:r.id()});}",
            draft.title, draft.project_id or "Reminders",
        )
        return Task(id=json.loads(out)["id"], title=draft.title, project_id=draft.project_id)

    def update_task(self, task_id: str, draft: TaskDraft) -> None:
        _jxa(
            "function run(argv){const R=Application('Reminders');"
            "const r=R.reminders.byId(argv[0]); r.name=argv[1];}",
            task_id, draft.title,
        )

    def complete_task(self, project_id: str | None, task_id: str) -> None:
        _jxa(
            "function run(argv){const R=Application('Reminders');"
            "R.reminders.byId(argv[0]).completed=true;}",
            task_id,
        )

    def close(self) -> None:
        pass
