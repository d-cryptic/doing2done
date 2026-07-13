"""Describe a handwritten page with a vision model: text vs diagram + caption."""
from __future__ import annotations

import base64
import json
from pathlib import Path

from ..retry import retrying_post

PROMPT = (
    "This is one page from a handwritten Apple Notes note. Return ONLY JSON:\n"
    '{"kind": "text" | "diagram" | "mixed",\n'
    ' "transcription": "verbatim text you can read (empty if none)",\n'
    ' "caption": "if it contains a diagram/sketch/flow, describe its MEANING and '
    'GOAL in 1-2 sentences; empty if it is plain text"}\n'
    "Distinguish handwritten prose from drawn diagrams. Be concise and faithful."
)


def describe_page(png_path: str | Path, *, api_key: str, model: str, base_url: str = "") -> dict:
    b64 = base64.b64encode(Path(png_path).read_bytes()).decode()
    url = (base_url or "https://api.openai.com/v1").rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    if "openrouter" in (base_url or ""):
        headers["HTTP-Referer"] = "https://github.com/d-cryptic/doing2done"
        headers["X-Title"] = "doing2done"
    r = retrying_post(
        url,
        headers=headers,
        timeout=90,
        json={
            "model": model,
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": PROMPT},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
                    ],
                }
            ],
        },
    )
    data = json.loads(r.json()["choices"][0]["message"]["content"])
    return {
        "kind": str(data.get("kind", "")).strip(),
        "transcription": str(data.get("transcription", "")).strip(),
        "caption": str(data.get("caption", "")).strip(),
    }
