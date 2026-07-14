"""Canary — detect SILENT failures (the worst kind: the loop runs but does nothing).

Guards: Apple Notes readable (FDA can break), note count collapse, todo provider
reachable, edge worker alive, and sync recency.
"""
from __future__ import annotations

import datetime as dt

import httpx

from .config import Settings
from .state import State


def check(settings: Settings, state: State) -> list[str]:
    """Return a list of problems (empty == healthy)."""
    problems: list[str] = []

    # 1) Apple Notes readable, and the count hasn't collapsed (self-calibrating).
    seen = -1
    try:
        from .notes import store

        seen = len(store.list_notes())
    except Exception as e:
        problems.append(f"cannot read Apple Notes ({type(e).__name__}) — Full Disk Access?")
    if seen == 0:
        problems.append("0 notes visible")
    if seen > 0:
        known = int(state.get_kv("note_count") or 0)
        if known and seen < known * 0.5:
            problems.append(f"note count collapsed: {seen} (was {known})")
        state.set_kv("note_count", str(seen))

    # 2) Todo provider reachable (expired token = silent no-op).
    try:
        from .providers import build_provider

        prov = build_provider(settings, state)
        if prov is None:
            problems.append("no todo provider configured / token missing")
        else:
            prov.list_projects()
            prov.close()
    except Exception as e:
        problems.append(f"todo provider unreachable ({type(e).__name__})")

    # 3) Edge worker alive.
    if settings.worker_url:
        try:
            httpx.get(f"{settings.worker_url}/health", timeout=15).raise_for_status()
        except Exception:
            problems.append("edge worker unreachable")

    # 4) Sync recency — the loop itself may have stopped.
    last = state.get_kv("last_sync")
    if last:
        try:
            age = dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(last)
            if age > dt.timedelta(hours=2):
                problems.append(f"no successful sync for {int(age.total_seconds() // 3600)}h")
        except ValueError:
            pass
    return problems


def mark_sync(state: State) -> None:
    state.set_kv("last_sync", dt.datetime.now(dt.UTC).isoformat())
