"""Typed settings loaded from environment / .env (never hardcode secrets)."""
from __future__ import annotations

import subprocess
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # ── TickTick (register at https://developer.ticktick.com/manage) ──
    ticktick_client_id: str = ""
    ticktick_client_secret: str = ""
    ticktick_redirect_uri: str = "http://localhost:8080/callback"
    ticktick_token_path: str = ".ticktick_token.json"
    ticktick_default_project_id: str = ""  # empty -> Inbox

    # ── Cloudflare (from .env, provisioned by you) ──
    cf_admin_api_token: str = ""
    cf_access_client_id: str = ""
    cf_access_client_secret: str = ""
    cf_account_id: str = "REDACTED_ACCOUNT_ID"
    cf_pages_project: str = "doing2done-vault"
    cf_access_allowed_email: str = "redacted@example.com"

    # ── LLM classifier (cheap model) ──
    llm_provider: str = "openai"  # openai(-compatible) | gemini
    llm_base_url: str = "https://openrouter.ai/api/v1"
    llm_api_key: str = ""
    openrouter_api_key: str = ""  # alias fallback
    llm_model: str = "google/gemini-2.5-flash"

    # ── Local paths ──
    notes_source: str = "store"  # store (FDA-only, no Automation) | jxa
    state_db: str = "data/state.db"
    exports_dir: str = "exports"
    vault_dir: str = "../doing2done-vault"
    vault_notes_dir: str = "../doing2done-vault/docs/notes"


    @model_validator(mode="after")
    def _fill_llm_key(self) -> Settings:
        if not self.llm_api_key and self.openrouter_api_key:
            object.__setattr__(self, "llm_api_key", self.openrouter_api_key)
        return self


def _resolve_op(value: str) -> str:
    """Resolve a 1Password `op://vault/item/field` reference via the op CLI."""
    if not value.startswith("op://"):
        return value
    try:
        out = subprocess.run(
            ["op", "read", value], capture_output=True, text=True, timeout=20
        )
        return out.stdout.strip() if out.returncode == 0 else value
    except Exception:
        return value


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    # Any field may be a 1Password reference (op://...) — resolve at runtime.
    for name, val in list(s.__dict__.items()):
        if isinstance(val, str) and val.startswith("op://"):
            object.__setattr__(s, name, _resolve_op(val))
    return s
