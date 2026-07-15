"""Verify the vault's internal links resolve.

VitePress fails a build on a dead *markdown* link, but the generated dashboards
(front page, notes index, duplicates, tags, timeline) emit raw HTML anchors, which
its checker ignores entirely. Those are exactly the links most at risk: a note's
stem contains its title, so any retitle renames the file and strands every anchor
pointing at the old one.
"""
from __future__ import annotations

import re
from pathlib import Path

_ANCHOR = re.compile(r'<a[^>]+href="(\./[^"#?]+)"')
_MD_LINK = re.compile(r"\]\((\./[^)#?]+)\)")


def _pages(docs: Path) -> set[str]:
    out: set[str] = set()
    for md in docs.rglob("*.md"):
        rel = str(md.relative_to(docs).with_suffix(""))
        out.add("/" + rel)
        if rel.endswith("index"):
            out.add("/" + rel[: -len("index")].rstrip("/"))
    return out


def _resolve(src: Path, docs: Path, href: str) -> str:
    base = "/" + str(src.relative_to(docs).parent).strip(".").strip("/")
    href = href[2:] if href.startswith("./") else href
    return ("/" + f"{base}/{href}".strip("/")).replace("//", "/").rstrip("/") or "/"


def broken_links(docs_dir: str) -> list[tuple[str, str]]:
    """[(page, href)] for every internal link that resolves to nothing."""
    docs = Path(docs_dir)
    if not docs.exists():
        return []
    pages = _pages(docs)
    out: list[tuple[str, str]] = []
    for md in docs.rglob("*.md"):
        txt = md.read_text()
        for pat in (_ANCHOR, _MD_LINK):
            for href in pat.findall(txt):
                if href.startswith("./assets/"):
                    continue  # images, not pages
                target = _resolve(md, docs, href)
                if target not in pages and target.rstrip("/") not in pages:
                    out.append((md.name, href))
    return out
