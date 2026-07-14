"""Token/cost accounting — append-only usage log + pricing from OpenRouter."""
from __future__ import annotations

import datetime as dt
import json
from collections import defaultdict
from pathlib import Path

import httpx

LOG = Path("data/usage.jsonl")


def record(model: str, usage: dict | None, kind: str = "text") -> None:
    """Append one LLM call's usage. Never raises (accounting must not break the run)."""
    if not usage:
        return
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        row = {
            "ts": dt.datetime.now(dt.UTC).isoformat(),
            "model": model,
            "kind": kind,
            "in": usage.get("prompt_tokens") or usage.get("promptTokenCount") or 0,
            "out": usage.get("completion_tokens") or usage.get("candidatesTokenCount") or 0,
        }
        with LOG.open("a") as f:
            f.write(json.dumps(row) + "\n")
    except Exception:
        pass


def _pricing() -> dict[str, tuple[float, float]]:
    """model -> ($/token in, $/token out) from OpenRouter."""
    try:
        r = httpx.get("https://openrouter.ai/api/v1/models", timeout=20)
        r.raise_for_status()
        out = {}
        for m in r.json().get("data", []):
            p = m.get("pricing") or {}
            try:
                out[m["id"]] = (float(p.get("prompt", 0)), float(p.get("completion", 0)))
            except (TypeError, ValueError):
                continue
        return out
    except Exception:
        return {}


def summarize(days: int = 30) -> dict:
    """Aggregate usage over the last N days with an estimated cost."""
    if not LOG.exists():
        return {"calls": 0, "models": {}, "total_cost": 0.0, "days": days}
    cutoff = dt.datetime.now(dt.UTC) - dt.timedelta(days=days)
    agg: dict[str, dict] = defaultdict(lambda: {"calls": 0, "in": 0, "out": 0})
    for line in LOG.read_text().splitlines():
        try:
            row = json.loads(line)
            if dt.datetime.fromisoformat(row["ts"]) < cutoff:
                continue
        except Exception:
            continue
        a = agg[row["model"]]
        a["calls"] += 1
        a["in"] += int(row.get("in", 0))
        a["out"] += int(row.get("out", 0))

    prices = _pricing()
    total = 0.0
    for model, a in agg.items():
        pin, pout = prices.get(model, (0.0, 0.0))
        a["cost"] = a["in"] * pin + a["out"] * pout
        total += a["cost"]
    return {
        "calls": sum(a["calls"] for a in agg.values()),
        "models": dict(agg),
        "total_cost": total,
        "days": days,
    }
