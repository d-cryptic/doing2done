"""The markdown provider ships as a zero-dependency backend but was never exercised."""
from __future__ import annotations

from doing2done.providers.base import TaskDraft
from doing2done.providers.markdown import MarkdownProvider


def _p(tmp_path):
    return MarkdownProvider(str(tmp_path / "todos.md"))


def test_due_date_is_not_part_of_the_title(tmp_path):
    """It's rendered as '(due ...)'; reading it back into the title leaked it into
    the daily brief and into any title comparison."""
    p = _p(tmp_path)
    p.create_task(TaskDraft(title="buy milk", due_date="2026-07-20"))
    t = p.open_tasks("Inbox")[0]
    assert t.title == "buy milk"
    assert t.due_date == "2026-07-20"


def test_update_keeps_an_existing_due_date(tmp_path):
    """update_task rebuilt the line from the title alone and dropped the due date."""
    p = _p(tmp_path)
    a = p.create_task(TaskDraft(title="buy milk", due_date="2026-07-20"))
    p.update_task(a.id, TaskDraft(title="buy oat milk"))
    t = p.open_tasks("Inbox")[0]
    assert t.title == "buy oat milk"
    assert t.due_date == "2026-07-20", "the due date was silently lost"


def test_update_can_change_the_due_date(tmp_path):
    p = _p(tmp_path)
    a = p.create_task(TaskDraft(title="x", due_date="2026-07-20"))
    p.update_task(a.id, TaskDraft(title="x", due_date="2026-08-01"))
    assert p.open_tasks("Inbox")[0].due_date == "2026-08-01"


def test_task_without_a_due_date(tmp_path):
    p = _p(tmp_path)
    p.create_task(TaskDraft(title="someday"))
    t = p.open_tasks("Inbox")[0]
    assert t.title == "someday" and not t.due_date


def test_complete_removes_it_from_open(tmp_path):
    p = _p(tmp_path)
    a = p.create_task(TaskDraft(title="done soon"))
    p.create_task(TaskDraft(title="still open"))
    p.complete_task("Inbox", a.id)
    assert [t.title for t in p.open_tasks("Inbox")] == ["still open"]


def test_state_survives_reopening_the_file(tmp_path):
    """The file is the database; a new process must see the same thing."""
    p = _p(tmp_path)
    p.create_task(TaskDraft(title="persisted", due_date="2026-07-20"))
    again = MarkdownProvider(str(tmp_path / "todos.md")).open_tasks("Inbox")
    assert [(t.title, t.due_date) for t in again] == [("persisted", "2026-07-20")]


def test_a_title_containing_the_word_due_is_untouched(tmp_path):
    """Only the rendered suffix is a due date — prose must survive."""
    p = _p(tmp_path)
    p.create_task(TaskDraft(title="pay what is due to the landlord"))
    assert p.open_tasks("Inbox")[0].title == "pay what is due to the landlord"
