"""Failure alerting via Telegram and/or Pushover (best-effort, env-configured)."""
from __future__ import annotations

import os

import httpx


def send_telegram(text: str, *, markdown: bool = True) -> bool:
    """Send text to your own chat verbatim (no prefix). True if it landed."""
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (tok and chat):
        return False
    payload = {"chat_id": chat, "text": text, "disable_web_page_preview": True}
    if markdown:
        payload["parse_mode"] = "Markdown"
    try:
        r = httpx.post(
            f"https://api.telegram.org/bot{tok}/sendMessage", json=payload, timeout=20
        )
        if not r.json().get("ok") and markdown:
            # Markdown is strict — a stray _ or * in a note title shouldn't lose the push.
            payload.pop("parse_mode")
            r = httpx.post(
                f"https://api.telegram.org/bot{tok}/sendMessage", json=payload, timeout=20
            )
        return bool(r.json().get("ok"))
    except Exception:
        return False


def notify(message: str) -> None:
    """Send an alert to any configured channel. Never raises."""
    tok, chat = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if tok and chat:
        try:
            httpx.post(
                f"https://api.telegram.org/bot{tok}/sendMessage",
                json={"chat_id": chat, "text": f"doing2done: {message}"},
                timeout=15,
            )
        except Exception:
            pass
    ptok, puser = os.environ.get("PUSHOVER_TOKEN"), os.environ.get("PUSHOVER_USER")
    if ptok and puser:
        try:
            httpx.post(
                "https://api.pushover.net/1/messages.json",
                data={"token": ptok, "user": puser, "message": f"doing2done: {message}"},
                timeout=15,
            )
        except Exception:
            pass
