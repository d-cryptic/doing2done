from doing2done.state import State, item_key


def test_dedup_roundtrip(tmp_path):
    db = State(str(tmp_path / "s.db"))
    assert db.get_task_id("n1", "Call vendor") is None
    db.remember_task("n1", "Call vendor", "task-123")
    assert db.get_task_id("n1", "Call vendor") == "task-123"


def test_note_watermark(tmp_path):
    db = State(str(tmp_path / "s.db"))
    assert db.note_needs_processing("n1", "2026-07-12T10:00:00Z") is True
    db.mark_note("n1", "2026-07-12T10:00:00Z", None)
    assert db.note_needs_processing("n1", "2026-07-12T10:00:00Z") is False
    assert db.note_needs_processing("n1", "2026-07-12T11:00:00Z") is True


def test_item_key_stable():
    assert item_key("n1", "x") == item_key("n1", "x")
    assert item_key("n1", "x") != item_key("n2", "x")
