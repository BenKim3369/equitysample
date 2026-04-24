from __future__ import annotations

import os
from pathlib import Path

import requests

TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"
MAX_TELEGRAM_MESSAGE_LENGTH = 4096


def _chunk_message(text: str, limit: int = MAX_TELEGRAM_MESSAGE_LENGTH) -> list[str]:
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].strip()

    if remaining:
        chunks.append(remaining)
    return chunks


def _warn(message: str) -> None:
    print(f"[WARN] {message}")


def send_markdown_to_telegram(markdown_path: Path) -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()

    if not chat_id:
        _warn("TELEGRAM_CHAT_ID is not set. Skipping Telegram delivery for safety.")
        return 0

    if not token:
        _warn("TELEGRAM_BOT_TOKEN is not set. Skipping Telegram delivery.")
        return 0

    if not markdown_path.exists():
        _warn(f"Markdown output does not exist: {markdown_path}")
        return 0

    text = markdown_path.read_text(encoding="utf-8")
    chunks = _chunk_message(text)
    endpoint = TELEGRAM_API_URL.format(token=token)

    sent = 0
    for idx, chunk in enumerate(chunks, start=1):
        payload = {"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True}
        try:
            response = requests.post(endpoint, json=payload, timeout=20)
            response.raise_for_status()
        except requests.RequestException as exc:
            _warn(f"Telegram send failed at chunk {idx}/{len(chunks)}: {exc}")
            break
        sent += 1
    return sent
