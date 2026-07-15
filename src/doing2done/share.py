"""Share a single vault note behind an unguessable, revocable link.

Nothing is public unless you explicitly share it. The link is a 43-char token, the
page is noindex, and `d2d unshare` kills it. Notes are rendered to HTML here rather
than in the Worker so the edge never has to parse markdown — and so raw HTML in a
note can never become live markup on a public page.
"""
from __future__ import annotations

import datetime as dt
import re
import secrets
from pathlib import Path

from .config import Settings

TOKEN_BYTES = 32          # -> 43-char urlsafe token
DEFAULT_DAYS = 30         # links rot by default; --days 0 opts out


def _frontmatter(md: str) -> tuple[dict, str]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", md, re.S)
    if not m:
        return {}, md
    fm: dict = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fm[k.strip()] = v.strip().strip("\"'")
    return fm, m.group(2)


def find_note(notes_dir: str, query: str) -> Path | None:
    """Resolve a note by stem or a case-insensitive title/filename substring."""
    nd = Path(notes_dir)
    exact = nd / f"{query}.md"
    if exact.exists():
        return exact
    q = query.lower()
    hits = []
    for f in nd.glob("*.md"):
        if f.name == "index.md":
            continue
        fm, _ = _frontmatter(f.read_text())
        if q in f.stem.lower() or q in fm.get("title", "").lower():
            hits.append(f)
    if not hits:
        return None
    # Prefer the shortest match — "kubernetes" should find the note, not a superset.
    return sorted(hits, key=lambda f: len(f.stem))[0]


def render(md_body: str) -> str:
    """Markdown -> HTML with raw HTML disabled, so note content can't inject markup."""
    from markdown_it import MarkdownIt

    md = MarkdownIt("commonmark", {"html": False, "linkify": True, "typographer": True})
    md.enable(["table", "strikethrough"])
    return md.render(md_body)


def prepare(settings: Settings, path: Path, days: int = DEFAULT_DAYS) -> dict:
    """Build the payload for POST /share. Assets are stripped: they aren't public."""
    fm, body = _frontmatter(path.read_text())
    # Vault-relative links and images would 404 (or leak) off-site — drop them.
    body = re.sub(r"!\[[^\]]*\]\(\./assets/[^)]+\)", "", body)
    body = re.sub(r"\[([^\]]+)\]\(\./[^)]+\)", r"\1", body)
    body = re.sub(r"\n## Related\n(?:\n- .*)*\n?", "\n", body)
    return {
        "token": secrets.token_urlsafe(TOKEN_BYTES),
        "title": fm.get("title", path.stem),
        "html": render(body.strip()),
        "note_id": path.stem,
        "expires_at": (
            (dt.datetime.now(dt.UTC) + dt.timedelta(days=days)).isoformat()
            if days > 0 else None
        ),
    }
