"""Thin TickTick Open API client + idempotent upsert over the state map."""
from __future__ import annotations

import httpx

from ..state import State

BASE = "https://api.ticktick.com/open/v1"

# TickTick priority: 0 none, 1 low, 3 medium, 5 high
PRIORITY = {"none": 0, "low": 1, "medium": 3, "high": 5}


class TickTickClient:
    def __init__(self, access_token: str, state: State) -> None:
        self._http = httpx.Client(
            base_url=BASE,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
            transport=httpx.HTTPTransport(retries=3),
        )
        self.state = state

    # ── reads ──
    def projects(self) -> list[dict]:
        r = self._http.get("/project")
        r.raise_for_status()
        return r.json()

    def project_data(self, project_id: str) -> dict:
        r = self._http.get(f"/project/{project_id}/data")
        r.raise_for_status()
        return r.json()

    # ── writes ──
    def _create(self, body: dict) -> dict:
        r = self._http.post("/task", json=body)
        r.raise_for_status()
        return r.json()

    def _update(self, task_id: str, body: dict) -> None:
        r = self._http.post(f"/task/{task_id}", json={**body, "id": task_id})
        r.raise_for_status()

    def complete(self, project_id: str, task_id: str) -> None:
        r = self._http.post(f"/project/{project_id}/task/{task_id}/complete")
        r.raise_for_status()

    def upsert_task(
        self,
        note_id: str,
        title: str,
        *,
        content: str | None = None,
        due_date: str | None = None,
        priority: str = "none",
        project_id: str | None = None,
        items: list[str] | None = None,
    ) -> str:
        """Create or update a task, deduped by (note_id, title)."""
        body: dict = {"title": title, "priority": PRIORITY.get(priority, 0)}
        if content:
            body["content"] = content
        if due_date:
            body["dueDate"] = due_date
            # a non-midnight time -> timed task with a reminder at due time
            time_part = due_date.split("T")[1][:8] if "T" in due_date else ""
            if time_part and time_part != "00:00:00":
                body["isAllDay"] = False
                body["reminders"] = ["TRIGGER:PT0S"]
            else:
                body["isAllDay"] = True
        if project_id:
            body["projectId"] = project_id
        if items:
            body["items"] = [{"title": s} for s in items]

        existing = self.state.get_task(note_id, title)
        if existing:
            if existing["completed"]:
                return existing["task_id"]  # don't resurrect a completed task
            self._update(existing["task_id"], body)
            return existing["task_id"]
        created = self._create(body)
        self.state.remember_task(
            note_id, title, created["id"], created.get("projectId")
        )
        return created["id"]

    def close(self) -> None:
        self._http.close()
