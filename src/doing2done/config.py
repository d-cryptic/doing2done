"""Typed settings loaded from environment / .env (never hardcode secrets)."""
from __future__ import annotations

from functools import lru_cache

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
    cf_account_id: str = "1c63a21104bcdfd82af9644b7eeed833"
    cf_pages_project: str = "doing2done-vault"
    cf_access_allowed_email: str = "barundebnath91@gmail.com"

    # ── LLM classifier (cheap model) ──
    llm_provider: str = "gemini"  # gemini | openai
    llm_api_key: str = ""
    llm_model: str = "gemini-1.5-flash"

    # ── Local paths ──
    state_db: str = "data/state.db"
    exports_dir: str = "exports"
    vault_dir: str = "../doing2done-vault"
    vault_notes_dir: str = "../doing2done-vault/docs/notes"


@lru_cache
def get_settings() -> Settings:
    return Settings()
