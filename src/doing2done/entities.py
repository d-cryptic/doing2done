"""Recurring named entities across the vault — orgs, projects, tech, certs.

Cheap and local: no LLM call, no re-ingest. It leans on the shapes people actually
write names in — CamelCase (IgniteTech, ArgoCD) and short ALLCAPS acronyms (ISRO,
DRDO, CKAD). Deliberately NOT multi-word Title Case: in this vault that is almost
always a note-title cross-reference ("Daily Focus", "Rollover Tasks"), not an entity.

An entity earns a page section only if it appears in two or more distinct notes —
a one-off mention isn't a thread worth indexing.
"""
from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path

# CamelCase, or a 2-6 letter all-caps acronym.
_CAND = re.compile(r"\b([A-Z][a-z]+[A-Z][A-Za-z]*|[A-Z]{2,6})\b")

# Generic tokens that are noise as an "entity" — filler acronyms and doc scaffolding.
_STOP = {
    "TLDR", "TL", "DR", "AI", "OK", "US", "UK", "EU", "PR", "PRS", "CI", "CD", "DP",
    "RS", "QA", "EOD", "EOW", "ID", "URL", "API", "HTTP", "HTML", "CSS", "JS", "PDF",
    "FAQ", "GB", "MB", "KB", "TB", "AM", "PM", "IST", "UTC", "CH", "ERS",
}
_MIN_NOTES = 2


def _title(md: str) -> str:
    m = re.search(r'^title:\s*"?(.*?)"?\s*$', md, re.M)
    return (m.group(1).strip() if m else "").strip()


def _strip(md: str) -> str:
    md = re.sub(r"^---\n.*?\n---\n", "", md, flags=re.S)  # frontmatter
    return re.sub(r"<[^>]+>", " ", md)                     # tag chips + any html


def extract(notes_dir: str) -> dict[str, list[tuple[str, str]]]:
    """{entity: [(note_title, stem), ...]} for entities in >= _MIN_NOTES notes."""
    nd = Path(notes_dir)
    by_ent: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for md in nd.glob("*.md"):
        if md.name == "index.md":
            continue
        raw = md.read_text()
        title = _title(raw) or md.stem
        text = _strip(raw)
        for m in _CAND.finditer(text):
            e = m.group(1)
            if e not in _STOP:
                by_ent[e].add((title, md.stem))
    return {
        e: sorted(notes)
        for e, notes in by_ent.items()
        if len(notes) >= _MIN_NOTES
    }
