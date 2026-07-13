from pathlib import Path

from doing2done.providers.base import TaskDraft
from doing2done.providers.markdown import MarkdownProvider
from doing2done.state import State
from doing2done.todo import TodoService


def _svc(tmp_path):
    p = MarkdownProvider(str(tmp_path / "todos.md"))
    db = State(str(tmp_path / "s.db"))
    svc = TodoService(p, db)
    svc.load_projects()
    return p, svc


def test_markdown_provider_crud(tmp_path):
    p = MarkdownProvider(str(tmp_path / "todos.md"))
    t = p.create_task(TaskDraft(title="Buy milk", project_id="Home"))
    assert [x.title for x in p.open_tasks("Home")] == ["Buy milk"]
    p.complete_task("Home", t.id)
    assert p.open_tasks("Home") == []


def test_service_dedup_is_provider_agnostic(tmp_path):
    p, svc = _svc(tmp_path)
    a = svc.upsert("note:1", TaskDraft(title="Ship it", project_id="Work"))
    b = svc.upsert("note:1", TaskDraft(title="Ship it", project_id="Work"))
    assert a == b  # deduped, not duplicated
    assert len(p.open_tasks("Work")) == 1


def test_service_routing_resolves_project(tmp_path):
    p = MarkdownProvider(str(tmp_path / "todos.md"))
    Path(tmp_path / "todos.md").write_text("# Todos\n\n## Work\n\n## Personal\n")
    db = State(str(tmp_path / "s.db"))
    svc = TodoService(p, db)
    svc.load_projects()
    assert svc.resolve_pid("work") == "Work"
    assert svc.resolve_pid("personal") == "Personal"
