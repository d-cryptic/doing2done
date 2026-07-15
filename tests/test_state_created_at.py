"""created_at must survive re-ingest — it's the only signal for 'how long open?'."""
from __future__ import annotations

from doing2done.state import State, item_key


def _row(st: State, key: str):
    with st._conn() as c:
        return c.execute("SELECT * FROM task_map WHERE key = ?", (key,)).fetchone()


def test_reupsert_preserves_created_at_and_bumps_updated_at(tmp_path):
    st = State(str(tmp_path / "s.db"))
    st.remember_task("note1", "Buy milk", "task1", "proj1")
    key = item_key("note1", "Buy milk")
    first = _row(st, key)
    assert first["created_at"] is not None

    # Pretend this todo first appeared two weeks ago, then re-ingest it.
    with st._conn() as c:
        c.execute(
            "UPDATE task_map SET created_at = '2020-01-01 00:00:00', "
            "updated_at = '2020-01-01 00:00:00' WHERE key = ?", (key,)
        )
    st.remember_task("note1", "Buy milk", "task1", "proj1")

    again = _row(st, key)
    assert again["created_at"] == "2020-01-01 00:00:00", "re-ingest reset the age clock"
    assert again["updated_at"] != "2020-01-01 00:00:00", "updated_at should track the run"


def test_reupsert_updates_mutable_fields(tmp_path):
    st = State(str(tmp_path / "s.db"))
    st.remember_task("note1", "Buy milk", "task1", "proj1")
    st.remember_task("note1", "Buy milk", "task2", "proj2")  # task moved lists
    r = _row(st, item_key("note1", "Buy milk"))
    assert (r["task_id"], r["project_id"]) == ("task2", "proj2")


def test_stale_todos_uses_created_at_not_updated_at(tmp_path):
    """A todo open for months must surface even though ingest just touched it."""
    from doing2done.digest import _stale_todos

    st = State(str(tmp_path / "s.db"))
    st.remember_task("note1", "Old thing", "task1", "proj1")
    with st._conn() as c:
        c.execute(
            "UPDATE task_map SET created_at = '2020-01-01 00:00:00', "
            "updated_at = datetime('now')"  # ingest ran a second ago
        )
    lines = _stale_todos(st)
    assert any("Old thing" in ln for ln in lines), "stale todo hidden by fresh updated_at"


def test_fresh_todo_is_not_stale(tmp_path):
    from doing2done.digest import _stale_todos

    st = State(str(tmp_path / "s.db"))
    st.remember_task("note1", "New thing", "task1", "proj1")
    assert _stale_todos(st) == []
