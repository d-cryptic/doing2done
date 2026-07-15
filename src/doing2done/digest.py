"""Push summaries to you instead of waiting to be asked.

Two shapes, same delivery (Telegram):
  - digest:  a weekly review — what you captured, closed, and keep deferring.
  - surface: a nudge — todos going stale, notes gone dormant.
"""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from .config import Settings
from .state import State

STALE_DAYS = 14      # an open todo untouched this long is "going stale"
DORMANT_DAYS = 21    # a note not revisited this long is "dormant"
MAX_LINES = 8        # keep pushes skimmable on a phone


def _frontmatter(md: str) -> dict:
    """Parse the small subset of YAML the vault actually writes."""
    m = re.match(r"^---\n(.*?)\n---\n", md, re.S)
    if not m:
        return {}
    fm: dict = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        fm[k.strip()] = v.strip().strip("\"'")
    return fm


def _recent_notes(settings: Settings, days: int) -> list[tuple[str, str]]:
    """(title, summary) for notes dated within the window."""
    cutoff = dt.date.today() - dt.timedelta(days=days)
    out: list[tuple[str, str]] = []
    for md in Path(settings.vault_notes_dir).glob("*.md"):
        if md.name == "index.md":
            continue
        fm = _frontmatter(md.read_text())
        raw = (fm.get("date") or "").split("T")[0]
        try:
            if raw and dt.date.fromisoformat(raw) >= cutoff:
                out.append((fm.get("title", md.stem), fm.get("summary", "")))
        except ValueError:
            continue
    return out


def _themes(notes: list[tuple[str, str]], settings: Settings) -> str:
    """LLM: 2-4 one-line themes across the week. Empty string on any failure."""
    if not notes:
        return ""
    from .reports import _llm_markdown

    listing = "\n".join(f"- {t}: {s}" for t, s in notes[:60])
    prompt = (
        "These are my notes from the past week. Name the 2-4 threads that actually "
        "run through them. One line each, '- ' bullets, no preamble, no headings. "
        "Be specific and concrete; if there is no real thread, return fewer bullets. "
        'Return JSON {"markdown": string}.\n\n' + listing
    )
    try:
        body = _llm_markdown(prompt, settings)
    except Exception:
        return ""
    lines = [ln for ln in body.splitlines() if ln.strip().startswith("-")]
    return "\n".join(lines[:4])


def _open_todos(state: State) -> int:
    with state._conn() as c:
        return c.execute("SELECT COUNT(*) n FROM task_map WHERE completed = 0").fetchone()["n"]


def compose_digest(settings: Settings, state: State, days: int = 7) -> str:
    """A weekly review sized for a phone screen. '' when there's nothing to say.

    Deliberately does NOT report "todos closed": task_map only marks a task complete
    when reconciliation drops it from a note, so that count is dominated by bulk
    machine writes and says nothing about what you actually finished.
    """
    notes = _recent_notes(settings, days)
    open_n = _open_todos(state)
    chronic = state.chronic_tasks(4)
    if not notes and not chronic:
        return ""

    today = dt.date.today()
    since = today - dt.timedelta(days=days)
    out = [f"*Weekly review* · {since:%b %d}–{today:%b %d}", ""]
    out.append(f"{len(notes)} notes captured · {open_n} todos open")

    themes = _themes(notes, settings)
    if themes:
        out += ["", "*Threads*", themes]

    if chronic:
        out += ["", "*Kill list* — rolled over repeatedly"]
        out += [f"· {n}× {title}" for title, n in chronic[:MAX_LINES]]
        out.append("_Break these down or drop them._")
    return "\n".join(out)


def _stale_todos(state: State, limit: int = MAX_LINES) -> list[str]:
    """Todos still open STALE_DAYS after they first appeared.

    Keyed on created_at, never updated_at: every ingest re-upserts live todos, so
    updated_at tracks the last pipeline run, not the last time you touched this.
    """
    cutoff = (dt.datetime.now() - dt.timedelta(days=STALE_DAYS)).isoformat(" ", "seconds")
    with state._conn() as c:
        rows = c.execute(
            "SELECT title, created_at FROM task_map "
            "WHERE completed = 0 AND created_at IS NOT NULL AND created_at < ? "
            "ORDER BY created_at LIMIT ?",
            (cutoff, limit),
        ).fetchall()
    out = []
    for r in rows:
        age = (dt.date.today() - dt.date.fromisoformat(r["created_at"][:10])).days
        out.append(f"· {r['title']} _({age}d)_")
    return out


def _dormant_notes(settings: Settings, limit: int = 4) -> list[str]:
    """Notes not touched in DORMANT_DAYS — ideas that went quiet."""
    cutoff = dt.date.today() - dt.timedelta(days=DORMANT_DAYS)
    aged: list[tuple[dt.date, str]] = []
    for md in Path(settings.vault_notes_dir).glob("*.md"):
        if md.name == "index.md":
            continue
        fm = _frontmatter(md.read_text())
        raw = (fm.get("date") or "").split("T")[0]
        try:
            d = dt.date.fromisoformat(raw) if raw else None
        except ValueError:
            continue
        if d and d < cutoff:
            aged.append((d, fm.get("title", md.stem)))
    aged.sort(reverse=True)  # most recently dormant first — still plausibly live
    return [f"· {t} _({(dt.date.today() - d).days}d ago)_" for d, t in aged[:limit]]


def compose_surface(settings: Settings, state: State) -> str:
    """A nudge about what's going quiet. '' when nothing qualifies — stay silent."""
    stale = _stale_todos(state)
    dormant = _dormant_notes(settings)
    if not stale and not dormant:
        return ""
    out = ["*Still open*", ""]
    if stale:
        out.append(f"Untouched for {STALE_DAYS}+ days:")
        out += stale
    if dormant:
        if stale:
            out.append("")
        out.append("Ideas gone quiet:")
        out += dormant
    return "\n".join(out)
