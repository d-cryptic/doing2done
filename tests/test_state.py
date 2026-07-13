from doing2done.state import State, item_key


def test_dedup_roundtrip(tmp_path):
    db = State(str(tmp_path / "s.db"))
    assert db.get_task("n1", "Call vendor") is None
    db.remember_task("n1", "Call vendor", "task-123", "proj-1")
    row = db.get_task("n1", "Call vendor")
    assert row["task_id"] == "task-123"
    assert row["project_id"] == "proj-1"
    assert row["completed"] == 0


def test_removed_todo_flow(tmp_path):
    db = State(str(tmp_path / "s.db"))
    db.remember_task("n1", "A", "t1", "p1")
    db.remember_task("n1", "B", "t2", "p1")
    assert {r["task_id"] for r in db.tasks_for_note("n1")} == {"t1", "t2"}
    db.mark_task_completed(item_key("n1", "A"))
    assert {r["task_id"] for r in db.tasks_for_note("n1")} == {"t2"}


def test_note_watermark(tmp_path):
    db = State(str(tmp_path / "s.db"))
    assert db.note_needs_processing("n1", "2026-07-12T10:00:00Z") is True
    db.mark_note("n1", "2026-07-12T10:00:00Z", None)
    assert db.note_needs_processing("n1", "2026-07-12T10:00:00Z") is False
    assert db.note_needs_processing("n1", "2026-07-12T11:00:00Z") is True


def test_item_key_stable():
    assert item_key("n1", "x") == item_key("n1", "x")
    assert item_key("n1", "x") != item_key("n2", "x")
