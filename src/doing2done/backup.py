"""Back up the state DB to R2 — it's the only copy of the dedup map.

Losing state.db means every note re-creates its todos (duplicate explosion), plus
loss of rollover history and push hashes. Snapshot daily, keep a `latest` pointer.
"""
from __future__ import annotations

import datetime as dt
import os
import subprocess
from pathlib import Path

from .config import Settings


def _env(settings: Settings) -> dict:
    env = {**os.environ, "CLOUDFLARE_API_TOKEN": settings.cf_admin_api_token}
    if settings.cf_account_id:
        env["CLOUDFLARE_ACCOUNT_ID"] = settings.cf_account_id
    return env


def _r2(settings: Settings, args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["wrangler", "r2", "object", *args, "--remote"],
        cwd=str(Path(settings.vault_dir).parent / "doing2done" / "worker"),
        env=_env(settings), capture_output=True, text=True,
    )


def backup(settings: Settings) -> list[str]:
    """Upload state.db to R2 as a dated snapshot + `latest`. Returns keys written."""
    db = Path(settings.state_db)
    if not db.exists():
        raise FileNotFoundError(f"no state db at {db}")
    bucket = settings.r2_bucket
    stamp = dt.date.today().isoformat()
    keys = [f"state/state-{stamp}.db", "state/latest.db"]
    for key in keys:
        r = _r2(settings, ["put", f"{bucket}/{key}", "--file", str(db.resolve())])
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout)[-300:])
    return keys


def restore(settings: Settings, key: str = "state/latest.db") -> str:
    """Download a state snapshot from R2 over the local state.db."""
    db = Path(settings.state_db)
    db.parent.mkdir(parents=True, exist_ok=True)
    r = _r2(settings, ["get", f"{settings.r2_bucket}/{key}", "--file", str(db.resolve())])
    if r.returncode != 0:
        raise RuntimeError((r.stderr or r.stdout)[-300:])
    return str(db)
