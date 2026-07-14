"""Turn your own notes into publishable drafts (RAG over the vault)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from .ask import _index, retrieve
from .config import Settings

_KINDS = {
    "tweet": "a punchy tweet thread (3-6 tweets, no hashtags, concrete and specific)",
    "blog": "a blog post draft with a title, intro, 2-4 sections, and a short conclusion",
    "note": "a tight explainer (300 words max)",
}


def make_draft(topic: str, kind: str, notes_dir: str, settings: Settings) -> tuple[str, str]:
    """Return (markdown, path). Uses ONLY your notes as source material."""
    from .classify.classifier import _gemini, _openai

    hits = retrieve(topic, _index(notes_dir), k=6)
    if not hits:
        return "", ""
    context = "\n\n".join(f"### {d['title']}\n{d['body'][:1500]}" for d in hits)
    style = _KINDS.get(kind, _KINDS["blog"])
    prompt = (
        f"Using ONLY the notes below as source material, write {style} about: {topic}.\n"
        "Ground every claim in the notes; do not invent facts. Keep the author's voice.\n"
        f'Return JSON {{"markdown": string}}.\n\nNotes:\n{context}'
    )
    if settings.llm_provider == "gemini":
        raw = _gemini(prompt, settings.llm_api_key, settings.llm_model)
    else:
        raw = _openai(prompt, settings.llm_api_key, settings.llm_model, settings.llm_base_url)
    try:
        body = json.loads(raw).get("markdown", "")
    except json.JSONDecodeError:
        body = raw
    slug = re.sub(r"[^a-z0-9]+", "-", topic.lower()).strip("-")[:50] or "draft"
    d = Path(notes_dir).parent / "drafts"
    d.mkdir(parents=True, exist_ok=True)
    dest = d / f"{kind}-{slug}.md"
    sources = ", ".join(h["title"] for h in hits)
    dest.write_text(
        f'---\ntitle: "{kind}: {topic}"\n---\n\n{body}\n\n---\n*Sources: {sources}*\n'
    )
    return body, str(dest)
