"""Daily note + rollover: build a morning brief from TickTick and write it out.

Pulls incomplete + overdue tasks, rolls them into a templated daily note, and
writes it to Apple Notes (JXA — needs Automation) and/or the vault.
"""
from __future__ import annotations

import datetime as dt
import subprocess

from .state import State
from .todo import TodoService

TEMPLATE_SECTIONS = ("🎯 Focus (top 3)", "📋 Rolled over", "📝 Notes", "✅ Done")


def _today() -> dt.date:
    return dt.date.today()


def _parse_due(s: str | None) -> dt.date | None:
    if not s:
        return None
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).date()
    except ValueError:
        return None


def build_brief(
    svc: TodoService,
    today: dt.date | None = None,
    state: State | None = None,
    settings=None,
) -> tuple[str, str]:
    """Return (title, markdown) for today's brief with rolled-over tasks."""
    today = today or _today()
    pairs = svc.open_with_project()  # [(Task, project_name)]

    def rollovers(task) -> int:
        return state.rollover_count(task.id) if state is not None else 0

    def line(task, pname: str) -> str:
        due = _parse_due(task.due_date)
        tag = ""
        if due and due < today:
            tag = f" ·  overdue {(today - due).days}d"
        elif due == today:
            tag = " ·  due today"
        n = rollovers(task)
        chronic = f"  ⚠️ rolled over {n}×" if n >= 3 else ""
        return f"- [ ] {task.title.strip()}  ({pname}{tag}){chronic}"

    def score(task) -> float:
        due = _parse_due(task.due_date)
        urgency = 2 if (due and due < today) else 1 if due == today else 0
        return urgency + task.priority / 5.0

    def quadrant(task) -> str:
        due = _parse_due(task.due_date)
        urgent = bool(due and due <= today)
        important = task.priority >= 3
        return {(True, True): "Q1 do-now", (False, True): "Q2 schedule",
                (True, False): "Q3 quick", (False, False): "Q4 later"}[(urgent, important)]

    overdue = [(t, n) for t, n in pairs if (_parse_due(t.due_date) or today) < today]
    if state is not None:
        for t_, _n in overdue:
            state.bump_rollover(t_.id, today.isoformat())
    due_today = [(t, n) for t, n in pairs if _parse_due(t.due_date) == today]
    high = [(t, n) for t, n in pairs if t.priority >= 5]

    focus_pool = sorted(overdue + due_today + high, key=lambda p: score(p[0]), reverse=True)
    seen: set[str] = set()
    focus = []
    for task, name in focus_pool:
        if task.id not in seen:
            seen.add(task.id)
            focus.append((task, name, quadrant(task)))
        if len(focus) == 3:
            break

    focus_ids = {t.id for t, _, _ in focus}
    rolled = [(t, n) for t, n in overdue if t.id not in focus_ids]

    title = f"Daily — {today.isoformat()}"
    md = [f"# {title}\n"]
    md.append(
        "## 🎯 Focus (top 3)\n"
        + ("\n".join(f"{line(t, n)}  `{q}`" for t, n, q in focus) or "- [ ] ")
    )
    if settings is not None:
        plan_lines = [
            f"- {t.title} | {n} | overdue {(today - (_parse_due(t.due_date) or today)).days}d "
            f"| priority {t.priority} | rolled over {rollovers(t)}x"
            for t, n in (overdue + due_today)[:25]
        ]
        plan = _plan(plan_lines, settings)
        if plan:
            md.append("\n## 🧭 Plan\n" + plan)
    md.append(
        "\n## 📋 Rolled over\n"
        + ("\n".join(line(t, n) for t, n in rolled) or "*nothing overdue 🎉*")
    )
    md.append("\n## 📝 Notes\n\n")
    done = [r["title"] for r in state.recently_completed(1)] if state is not None else []
    md.append("## ✅ Done\n" + ("\n".join(f"- [x] {d}" for d in done) if done else "*nothing yet*"))
    return title, "\n".join(md)


def _plan(lines: list[str], settings) -> str:
    """LLM planning pass: a realistic 'today' given the open work. Best-effort."""
    if not lines or not settings.llm_api_key:
        return ""
    from .classify.classifier import _gemini, _openai

    prompt = (
        "You are a pragmatic planning assistant. Given today's open tasks (with overdue "
        "days, priority, and how many times each has been rolled over), write 2-4 short "
        "sentences: what to realistically do today, what to explicitly drop/defer, and "
        "call out anything rolled over many times that should be broken down or killed. "
        'Be direct, no preamble. Return JSON {"markdown": string}.\n\n' + "\n".join(lines)
    )
    import json

    try:
        if settings.llm_provider == "gemini":
            raw = _gemini(prompt, settings.llm_api_key, settings.llm_model)
        else:
            raw = _openai(prompt, settings.llm_api_key, settings.llm_model, settings.llm_base_url)
        return json.loads(raw).get("markdown", "")
    except Exception:
        return ""


def _md_to_html(md: str) -> str:
    html = []
    for ln in md.splitlines():
        if ln.startswith("# "):
            html.append(f"<h1>{ln[2:]}</h1>")
        elif ln.startswith("## "):
            html.append(f"<h2>{ln[3:]}</h2>")
        elif ln.startswith("- [ ] "):
            html.append(f"<div>☐ {ln[6:]}</div>")
        elif ln.strip():
            html.append(f"<div>{ln}</div>")
        else:
            html.append("<br>")
    return "".join(html)


_JXA_CREATE = """
function run(argv) {
  const [title, html, folderName] = argv;
  const Notes = Application('Notes');
  let folder;
  try { folder = Notes.folders.byName(folderName); folder.name(); }
  catch (e) { folder = Notes.make({new: 'folder', withProperties: {name: folderName}}); }
  // skip if a note with this title already exists in the folder (idempotent per day)
  const existing = folder.notes.whose({name: title})();
  if (existing.length) return 'exists';
  Notes.make({new: 'note', at: folder, withProperties: {body: html}});
  return 'created';
}
"""


def write_to_apple_notes(title: str, md: str, folder: str = "Daily") -> str:
    """Create the daily note in Apple Notes (needs Automation permission)."""
    html = f"<h1>{title}</h1>" + _md_to_html("\n".join(md.splitlines()[1:]))
    proc = subprocess.run(
        ["osascript", "-l", "JavaScript", "-e", _JXA_CREATE, title, html, folder],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "osascript failed")
    return proc.stdout.strip()
