"""TickTick Open API provider."""
from __future__ import annotations

import httpx

from .base import PRIORITY, Project, Task, TaskDraft

BASE = "https://api.ticktick.com/open/v1"


class TickTickProvider:
    name = "ticktick"

    def __init__(self, access_token: str) -> None:
        self._http = httpx.Client(
            base_url=BASE,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
            transport=httpx.HTTPTransport(retries=3),
        )

    def _body(self, d: TaskDraft) -> dict:
        body: dict = {"title": d.title, "priority": PRIORITY.get(d.priority, 0)}
        if d.content:
            body["content"] = d.content
        if d.project_id:
            body["projectId"] = d.project_id
        if d.due_date:
            body["dueDate"] = d.due_date
            time_part = d.due_date.split("T")[1][:8] if "T" in d.due_date else ""
            if time_part and time_part != "00:00:00":
                body["isAllDay"] = False
                body["reminders"] = ["TRIGGER:PT0S"]
            else:
                body["isAllDay"] = True
        if d.items:
            body["items"] = [{"title": s} for s in d.items]
        return body

    def list_projects(self) -> list[Project]:
        r = self._http.get("/project")
        r.raise_for_status()
        return [Project(id=p["id"], name=p["name"]) for p in r.json()]

    def open_tasks(self, project_id: str) -> list[Task]:
        r = self._http.get(f"/project/{project_id}/data")
        r.raise_for_status()
        out = []
        for t in r.json().get("tasks") or []:
            if t.get("status", 0) == 0:
                out.append(Task(
                    id=t["id"], title=t.get("title", ""), project_id=t.get("projectId"),
                    priority=t.get("priority", 0), due_date=t.get("dueDate"),
                ))
        return out

    def create_task(self, draft: TaskDraft) -> Task:
        r = self._http.post("/task", json=self._body(draft))
        r.raise_for_status()
        j = r.json()
        return Task(id=j["id"], title=draft.title, project_id=j.get("projectId"))

    def update_task(self, task_id: str, draft: TaskDraft) -> None:
        r = self._http.post(f"/task/{task_id}", json={**self._body(draft), "id": task_id})
        r.raise_for_status()

    def complete_task(self, project_id: str | None, task_id: str) -> None:
        if not project_id:
            return
        r = self._http.post(f"/project/{project_id}/task/{task_id}/complete")
        r.raise_for_status()

    def close(self) -> None:
        self._http.close()
