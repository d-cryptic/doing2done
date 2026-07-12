"""One cheap-LLM pass: OCR'd note text -> {todos[], markdown, title, date, tags}."""
from __future__ import annotations

import json

import httpx

from .models import NoteResult

SYSTEM = """You convert a raw note (OCR'd handwriting) into structured JSON.
Return ONLY JSON matching this schema:
{
  "title": string,
  "date": string|null,            // ISO date if the note implies one
  "tags": string[],
  "todos": [                      // extract every actionable item
    {"title": string, "due_date": string|null, "priority": "none|low|medium|high",
     "project": string|null}
  ],
  "markdown": string,             // the note body as clean markdown (exclude pure todo lists)
  "is_todo_only": boolean         // true if the note is ONLY action items, no prose worth archiving
}
Infer due_date from phrases like "by Friday". Keep markdown faithful but tidy."""


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


def _openai(text: str, api_key: str, model: str) -> str:
    r = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {api_key}"},
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


def classify_note(text: str, *, provider: str, api_key: str, model: str) -> NoteResult:
    if not api_key:
        raise RuntimeError("LLM_API_KEY not set — cannot classify.")
    raw = _gemini(text, api_key, model) if provider == "gemini" else _openai(text, api_key, model)
    return NoteResult.model_validate(json.loads(raw))
