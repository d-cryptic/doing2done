"""'Ask my notes' — TF-IDF retrieval over the vault + LLM synthesis (cited)."""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

from .classify.classifier import _gemini, _openai
from .config import Settings
from .relate import _frontmatter, _tokens


def _index(notes_dir: str) -> list[dict]:
    docs = []
    for f in Path(notes_dir).glob("*.md"):
        if f.name == "index.md":
            continue
        fm, body = _frontmatter(f.read_text())
        title = fm.get("title", f.stem)
        docs.append({"title": title, "body": body, "tf": Counter(_tokens(f"{title} {body}"))})
    return docs


def retrieve(query: str, docs: list[dict], k: int = 6) -> list[dict]:
    if not docs:
        return []
    df: Counter = Counter()
    for d in docs:
        for term in d["tf"]:
            df[term] += 1
    n = len(docs)
    idf = {t: math.log(n / (1 + c)) + 1 for t, c in df.items()}
    q = Counter(_tokens(query))
    scored = []
    for d in docs:
        score = sum(q[t] * d["tf"].get(t, 0) * idf.get(t, 1.0) for t in q)
        if score > 0:
            scored.append((score, d))
    scored.sort(key=lambda x: -x[0])
    return [d for _, d in scored[:k]]


def ask(question: str, notes_dir: str, settings: Settings) -> dict:
    """Answer a question from the vault. Returns {answer, sources}."""
    hits = retrieve(question, _index(notes_dir))
    if not hits:
        return {"answer": "No relevant notes found.", "sources": []}
    context = "\n\n".join(f"### {d['title']}\n{d['body'][:1500]}" for d in hits)
    prompt = (
        "Answer the question using ONLY the notes below. Cite the note titles you used. "
        "If the notes don't contain the answer, say so.\n"
        f'Return JSON {{"answer": string, "sources": string[]}}.\n\n'
        f"Question: {question}\n\nNotes:\n{context}"
    )
    if settings.llm_provider == "gemini":
        raw = _gemini(prompt, settings.llm_api_key, settings.llm_model)
    else:
        raw = _openai(prompt, settings.llm_api_key, settings.llm_model, settings.llm_base_url)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"answer": raw, "sources": [d["title"] for d in hits]}
