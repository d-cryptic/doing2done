"""Link enrichment: fetch URLs found in notes, summarize, inject context."""
from __future__ import annotations

import json
import re
from pathlib import Path

import httpx

from .classify.classifier import _gemini, _openai
from .config import Settings

_URL_RE = re.compile(r"https?://[^\s<>)\]]+")
_SECTION = "## Link context"


def _fetch_text(url: str) -> str:
    try:
        r = httpx.get(url, timeout=15, follow_redirects=True)
        r.raise_for_status()
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", r.text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()[:4000]
    except Exception:
        return ""


def _summarize(url: str, text: str, s: Settings) -> str:
    if not text:
        return ""
    prompt = (
        f'Summarize this web page in 1-2 sentences for a note. Return JSON {{"summary": string}}.\n'
        f"URL: {url}\n\n{text}"
    )
    try:
        if s.llm_provider == "gemini":
            raw = _gemini(prompt, s.llm_api_key, s.llm_model)
        else:
            raw = _openai(prompt, s.llm_api_key, s.llm_model, s.llm_base_url)
        return json.loads(raw).get("summary", "")
    except Exception:
        return ""


def enrich_links(notes_dir: str, settings: Settings, limit: int | None = None) -> int:
    enriched = 0
    for f in Path(notes_dir).glob("*.md"):
        if f.name == "index.md":
            continue
        body = f.read_text()
        if _SECTION in body:
            continue  # already enriched (idempotent)
        urls = list(dict.fromkeys(_URL_RE.findall(body)))
        if not urls:
            continue
        lines = []
        for url in urls[:5]:
            summary = _summarize(url, _fetch_text(url), settings)
            if summary:
                lines.append(f"- <{url}> — {summary}")
        if lines:
            f.write_text(body.rstrip() + f"\n\n{_SECTION}\n\n" + "\n".join(lines) + "\n")
            enriched += 1
        if limit and enriched >= limit:
            break
    return enriched
