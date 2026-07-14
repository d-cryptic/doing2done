"""Back up the state DB to R2 — it's the only copy of the dedup map.

Losing state.db means every note re-creates its todos (duplicate explosion), plus
loss of rollover history and push hashes. Snapshot daily, keep a `latest` pointer.
"""
from __future__ import annotations

import datetime as dt
import os
import subprocess
import tempfile
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


def _crypt(src: Path, dst: Path, key: str, decrypt: bool = False) -> None:
    """AES-256 via openssl (pbkdf2). Task titles shouldn't sit in cold storage plaintext."""
    cmd = ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-salt"]
    if decrypt:
        cmd.append("-d")
    cmd += ["-in", str(src), "-out", str(dst), "-pass", f"pass:{key}"]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"openssl failed: {r.stderr[-200:]}")


def backup(settings: Settings) -> list[str]:
    """Upload state.db to R2 as a dated snapshot + `latest` (encrypted if a key is set)."""
    db = Path(settings.state_db)
    if not db.exists():
        raise FileNotFoundError(f"no state db at {db}")
    bucket = settings.r2_bucket
    stamp = dt.date.today().isoformat()
    suffix = ".db.enc" if settings.backup_key else ".db"
    keys = [f"state/state-{stamp}{suffix}", f"state/latest{suffix}"]

    with tempfile.TemporaryDirectory() as tmp:
        upload = db.resolve()
        if settings.backup_key:
            enc = Path(tmp) / "state.db.enc"
            _crypt(db, enc, settings.backup_key)
            upload = enc.resolve()
        for key in keys:
            r = _r2(settings, ["put", f"{bucket}/{key}", "--file", str(upload)])
            if r.returncode != 0:
                raise RuntimeError((r.stderr or r.stdout)[-300:])
    return keys


def restore(settings: Settings, key: str = "") -> str:
    """Download (and decrypt) a state snapshot from R2 over the local state.db."""
    db = Path(settings.state_db)
    db.parent.mkdir(parents=True, exist_ok=True)
    key = key or (f"state/latest{'.db.enc' if settings.backup_key else '.db'}")
    with tempfile.TemporaryDirectory() as tmp:
        landed = Path(tmp) / "download.bin" if settings.backup_key else db.resolve()
        r = _r2(settings, ["get", f"{settings.r2_bucket}/{key}", "--file", str(landed)])
        if r.returncode != 0:
            raise RuntimeError((r.stderr or r.stdout)[-300:])
        if settings.backup_key:
            _crypt(landed, db.resolve(), settings.backup_key, decrypt=True)
    return str(db)
