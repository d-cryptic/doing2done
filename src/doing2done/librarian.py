"""Nightly librarian — safe, autonomous vault gardening.

Repairs weak metadata (Untitled titles, missing tags, missing TL;DR) by re-deriving
it from the note's own body. Deliberately conservative: never renames files (the
filename carries the note identity), never rewrites the body, never merges notes.
"""
from __future__ import annotations

import re
from pathlib import Path

from .classify.classifier import classify_note
from .config import Settings
from .relate import _frontmatter
from .vault import render_frontmatter

_FM_RE = re.compile(r"^---\n.*?\n---\n", re.S)
_TLDR = "> **TL;DR**"


def _weaknesses(fm: dict, body: str) -> list[str]:
    out = []
    title = (fm.get("title") or "").strip()
    if not title or title.lower().startswith("untitled"):
        out.append("title")
    if not fm.get("tags"):
        out.append("tags")
    if _TLDR not in body:
        out.append("summary")
    return out


def garden(settings: Settings, apply: bool = False, limit: int | None = None) -> list[dict]:
    """Find (and optionally repair) notes with weak metadata."""
    notes = Path(settings.vault_notes_dir)
    report: list[dict] = []
    for md in sorted(notes.glob("*.md")):
        if md.name == "index.md":
            continue
        raw = md.read_text()
        fm, body = _frontmatter(raw)
        weak = _weaknesses(fm, body)
        if not weak:
            continue
        entry = {"file": md.name, "weak": weak, "fixed": False}
        if apply and body.strip():
            try:
                r = classify_note(
                    body[:8000], provider=settings.llm_provider, api_key=settings.llm_api_key,
                    model=settings.llm_model, base_url=settings.llm_base_url,
                )
                title = r.title if "title" in weak else (fm.get("title") or r.title)
                tags = r.tags if "tags" in weak else (fm.get("tags") or r.tags)
                new_body = body
                if "summary" in weak and r.summary:
                    new_body = f"{_TLDR} {r.summary}\n\n{body.lstrip()}"
                md.write_text(
                    render_frontmatter(title, fm.get("date", ""), tags) + new_body.strip() + "\n"
                )
                entry["fixed"] = True
            except Exception as e:
                entry["error"] = type(e).__name__
        report.append(entry)
        if limit and len(report) >= limit:
            break
    return report
