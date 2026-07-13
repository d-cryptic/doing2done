"""One cheap-LLM pass: OCR'd note text -> {todos[], markdown, title, date, tags}."""
from __future__ import annotations

import datetime as _dt
import json

import httpx

from .models import NoteResult

SYSTEM = """You convert a raw note (OCR'd handwriting) into structured JSON.
Return ONLY JSON matching this schema:
{
  "title": string,                // ALWAYS generate a concise, descriptive title (never "Untitled")
  "date": string|null,            // ISO date if the note implies one
  "tags": string[],               // 2-5 lowercase topical tags
  "summary": string,              // one-line TL;DR of what this note is about
  "links": string[],              // any URLs mentioned
  "todos": [                      // extract every actionable item
    {"title": string, "due_date": string|null, "priority": "none|low|medium|high",
     "project": string|null}
  ],
  "markdown": string,             // the note body as clean markdown (exclude pure todo lists)
  "is_todo_only": boolean         // true if ONLY action items, no prose worth archiving
}
Infer due_date from phrases like "by Friday". Generate a meaningful title even for
messy notes. Keep markdown faithful but tidy."""


def _gemini(text: str, api_key: str, model: str) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    r = httpx.post(
        url,
        params={"key": api_key},
        json={
            "systemInstruction": {"parts": [{"text": SYSTEM}]},
            "contents": [{"parts": [{"text": text}]}],
            "generationConfig": {"responseMimeType": "application/json"},
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


def _openai(text: str, api_key: str, model: str, base_url: str = "") -> str:
    url = (base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    if "openrouter" in (base_url or ""):
        headers["HTTP-Referer"] = "https://github.com/d-cryptic/doing2done"
        headers["X-Title"] = "doing2done"
    r = httpx.post(
        url,
        headers=headers,
        json={
            "model": model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": SYSTEM},
                {"role": "user", "content": text},
            ],
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def classify_note(
    text: str,
    *,
    provider: str,
    api_key: str,
    model: str,
    base_url: str = "",
    today: str | None = None,
    projects: list[str] | None = None,
) -> NoteResult:
    if not api_key:
        raise RuntimeError("LLM_API_KEY not set — cannot classify.")
    today = today or _dt.date.today().isoformat()
    parts = [f"Today is {today}. Resolve any relative dates against it."]
    if projects:
        parts.append(
            "Available TickTick lists — set each todo.project to the EXACT "
            "best-matching name from this list, or null for none: "
            + ", ".join(projects)
        )
    parts.append(text)
    dated = "\n\n".join(parts)
    last_err: Exception | None = None
    for _ in range(2):  # LLMs occasionally emit malformed JSON; retry once
        if provider == "gemini":
            raw = _gemini(dated, api_key, model)
        else:
            raw = _openai(dated, api_key, model, base_url)
        try:
            return NoteResult.model_validate(json.loads(raw))
        except (json.JSONDecodeError, ValueError) as e:
            last_err = e
    raise last_err if last_err else RuntimeError("classification failed")
