"""`d2d init` — scaffold a fresh clone: vault, .env, worker config."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .config import Settings


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def init_project(settings: Settings) -> list[str]:
    root = _repo_root()
    steps: list[str] = []

    vault = Path(settings.vault_dir)
    if not vault.exists():
        shutil.copytree(root / "vault-template", vault)
        try:
            subprocess.run(["git", "init", "-q"], cwd=vault, check=False)
        except Exception:
            pass
        steps.append(f"scaffolded vault -> {vault}")
    else:
        steps.append(f"vault already exists -> {vault} (skipped)")

    env = root / ".env"
    if not env.exists():
        shutil.copy(root / ".env.example", env)
        steps.append("created .env from .env.example (fill it in)")
    else:
        steps.append(".env already exists (skipped)")

    wt = root / "worker" / "wrangler.toml"
    if not wt.exists():
        shutil.copy(root / "worker" / "wrangler.toml.example", wt)
        steps.append("created worker/wrangler.toml (set database_id after provisioning)")
    else:
        steps.append("worker/wrangler.toml already exists (skipped)")

    return steps
