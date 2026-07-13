"""Daily note + rollover: build a morning brief from TickTick and write it out.

Pulls incomplete + overdue tasks, rolls them into a templated daily note, and
writes it to Apple Notes (JXA — needs Automation) and/or the vault.
"""
from __future__ import annotations

import datetime as dt
import subprocess

from .state import State
from .ticktick.client import TickTickClient

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


def collect_open_tasks(tt: TickTickClient) -> list[dict]:
    """All undone tasks across projects, with project name attached."""
    out: list[dict] = []
    for p in tt.projects():
        try:
            data = tt.project_data(p["id"])
        except Exception:
            continue
        for t in data.get("tasks") or []:
            if t.get("status", 0) == 0:  # 0 = not completed
                out.append({**t, "_project": p["name"]})
    return out


def build_brief(
    tt: TickTickClient, today: dt.date | None = None, state: State | None = None
) -> tuple[str, str]:
    """Return (title, markdown) for today's brief with rolled-over tasks."""
    today = today or _today()
    tasks = collect_open_tasks(tt)

    def line(t: dict) -> str:
        due = _parse_due(t.get("dueDate"))
        tag = ""
        if due and due < today:
            tag = f" ·  overdue {(today - due).days}d"
        elif due == today:
            tag = " ·  due today"
        return f"- [ ] {t.get('title', '').strip()}  ({t['_project']}{tag})"

    overdue = [t for t in tasks if (_parse_due(t.get("dueDate")) or today) < today]
    due_today = [t for t in tasks if _parse_due(t.get("dueDate")) == today]
    high = [t for t in tasks if t.get("priority", 0) >= 5]

    # focus = highest-priority overdue/today, up to 3
    focus_pool = sorted(
        overdue + due_today + high, key=lambda t: -t.get("priority", 0)
    )
    seen: set[str] = set()
    focus = []
    for t in focus_pool:
        if t["id"] not in seen:
            seen.add(t["id"])
            focus.append(t)
        if len(focus) == 3:
            break

    rolled = [t for t in overdue if t["id"] not in {f["id"] for f in focus}]

    title = f"Daily — {today.isoformat()}"
    md = [f"# {title}\n"]
    md.append("## 🎯 Focus (top 3)\n" + ("\n".join(line(t) for t in focus) or "- [ ] "))
    md.append(
        "\n## 📋 Rolled over\n" + ("\n".join(line(t) for t in rolled) or "*nothing overdue 🎉*")
    )
    md.append("\n## 📝 Notes\n\n")
    done = []
    if state is not None:
        done = [r["title"] for r in state.recently_completed(1)]
    md.append(
        "## ✅ Done\n"
        + ("\n".join(f"- [x] {t}" for t in done) if done else "*nothing yet*")
    )
    return title, "\n".join(md)


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
