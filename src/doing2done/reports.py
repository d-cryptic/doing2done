"""Vault reports: tag index page + weekly digest."""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from .config import Settings


def _llm_markdown(prompt: str, settings: Settings) -> str:
    """Call the LLM for a {markdown} JSON payload; retry once, fall back to raw."""
    import json

    from .classify.classifier import _gemini, _openai

    for _ in range(2):
        if settings.llm_provider == "gemini":
            raw = _gemini(prompt, settings.llm_api_key, settings.llm_model)
        else:
            raw = _openai(prompt, settings.llm_api_key, settings.llm_model, settings.llm_base_url)
        try:
            return json.loads(raw).get("markdown", "")
        except json.JSONDecodeError:
            last = raw
    return last  # best-effort raw text


def _frontmatter(md: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---", md, re.S)
    if not m:
        return {}
    fm: dict = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            items = [x.strip().strip('"').strip("'") for x in v[1:-1].split(",")]
            fm[k.strip()] = [x for x in items if x]
        else:
            fm[k.strip()] = v.strip('"').strip("'")
    return fm


def generate_tag_index(notes_dir: str) -> str:
    """Write docs/tags.md grouping every note by tag. Returns the path."""
    nd = Path(notes_dir)
    by_tag: dict[str, list[tuple[str, str]]] = {}
    for md in sorted(nd.glob("*.md")):
        if md.name == "index.md":
            continue
        fm = _frontmatter(md.read_text())
        title = fm.get("title", md.stem)
        for tag in fm.get("tags", []) or ["untagged"]:
            by_tag.setdefault(tag, []).append((title, md.stem))
    out = ["# Tags\n"]
    for tag in sorted(by_tag):
        out.append(f"\n## {tag}  ({len(by_tag[tag])})\n")
        for title, stem in sorted(by_tag[tag]):
            out.append(f"- [{title}](./notes/{stem})")
    dest = nd.parent / "tags.md"
    dest.write_text("\n".join(out) + "\n")
    return str(dest)


def weekly_digest(settings: Settings, days: int = 7) -> str:
    """Summarize the last N days of notes into a vault digest via the LLM."""

    nd = Path(settings.vault_notes_dir)
    cutoff = dt.date.today() - dt.timedelta(days=days)
    recent = []
    for md in nd.glob("*.md"):
        if md.name == "index.md":
            continue
        fm = _frontmatter(md.read_text())
        d = fm.get("date", "")
        try:
            if d and dt.date.fromisoformat(d.split("T")[0]) >= cutoff:
                recent.append((fm.get("title", md.stem), fm.get("summary", "")))
        except ValueError:
            continue
    if not recent:
        return ""
    listing = "\n".join(f"- {t}: {s}" for t, s in recent)
    prompt = (
        "Write a concise weekly review (markdown) from these note summaries. "
        "Group into themes, surface what's in progress and what needs attention. "
        f"Return JSON {{\"markdown\": string}}.\n\n{listing}"
    )

    body = _llm_markdown(prompt, settings)
    wk = nd / "weekly"
    wk.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    dest = wk / f"{today}.md"
    header = f'---\ntitle: "Weekly — {today}"\n---\n\n# Weekly review — {today}\n\n'
    dest.write_text(header + body + "\n")
    return str(dest)


def generate_duplicates_page(notes_dir: str) -> str:
    """Write docs/duplicates.md listing near-duplicate note pairs for review."""
    from .relate import find_duplicates

    pairs = find_duplicates(notes_dir)
    out = ["# Possible duplicates\n", "\nNear-duplicate notes to review/merge:\n"]
    if not pairs:
        out.append("\n*none found* 🎉")
    for a, b, sim in pairs:
        out.append(f"- **{sim}** — {a}  ~  {b}")
    dest = Path(notes_dir).parent / "duplicates.md"
    dest.write_text("\n".join(out) + "\n")
    return str(dest)


def generate_insights(settings: Settings) -> str:
    """LLM insight report over all notes: recurring themes, stale ideas, patterns."""

    nd = Path(settings.vault_notes_dir)
    items = []
    for md in nd.glob("*.md"):
        if md.name == "index.md":
            continue
        fm = _frontmatter(md.read_text())
        tags = ', '.join(fm.get('tags', []) or [])
        items.append(f"- {fm.get('title', md.stem)} [{tags}]: {fm.get('summary', '')}")
    if not items:
        return ""
    prompt = (
        "From these note titles/tags/summaries, produce a markdown insight report: "
        "recurring themes, what's in progress, stale ideas worth revisiting, and any patterns. "
        'Return JSON {"markdown": string}.\n\n' + "\n".join(items[:200])
    )
    body = _llm_markdown(prompt, settings)
    dest = nd.parent / "insights.md"
    dest.write_text(f"# Insights\n\n{body}\n")
    return str(dest)
