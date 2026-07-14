"""Eval harness — runs the classifier over golden cases and scores extraction quality."""
from __future__ import annotations

from dataclasses import dataclass, field

from .classify.classifier import classify_note
from .config import Settings


@dataclass
class CaseResult:
    name: str
    ok: bool
    missing: list[str] = field(default_factory=list)
    leaked: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    got: list[str] = field(default_factory=list)


def run_case(case: dict, settings: Settings) -> CaseResult:
    r = classify_note(
        case["text"], provider=settings.llm_provider, api_key=settings.llm_api_key,
        model=settings.llm_model, base_url=settings.llm_base_url,
    )
    titles = [t.title for t in r.todos]
    blob = " | ".join(titles).lower()
    missing = [p for p in case.get("expect_todos", []) if p.lower() not in blob]
    leaked = [p for p in case.get("forbid_todos", []) if p.lower() in blob]
    notes: list[str] = []

    if "max_todos" in case and len(r.todos) > case["max_todos"]:
        notes.append(f"too many todos: {len(r.todos)} > {case['max_todos']}")
    if case.get("expect_time"):
        if not any(t.due_date and "T" in t.due_date and t.due_date.split("T")[1][:5] != "00:00"
                   for t in r.todos):
            notes.append("expected a time on due_date")
    if case.get("expect_subtasks"):
        if not any(t.items for t in r.todos):
            notes.append("expected subtasks (items)")

    ok = not missing and not leaked and not notes
    return CaseResult(case["name"], ok, missing, leaked, notes, titles)


def _load_cases() -> list[dict]:
    """Load golden cases from evals/cases.py at the repo root (cwd-independent)."""
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "evals" / "cases.py"
    spec = importlib.util.spec_from_file_location("d2d_eval_cases", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load eval cases from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return list(mod.CASES)


def run_evals(settings: Settings) -> list[CaseResult]:
    return [run_case(c, settings) for c in _load_cases()]
