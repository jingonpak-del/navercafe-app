from __future__ import annotations

import base64
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class StoredCookieBundle:
    cookies: list[dict[str, Any]]
    saved_at: str
    username_hint: str = ""


class SessionStore:
    """Persist Selenium/Naver cookies for reuse between daily crawler runs.

    The store supports two formats:
    - plaintext JSON when no encryption key is provided;
    - lightweight key-derived XOR encoding when a key is provided.

    The encoded format is not a substitute for OS keychain-grade encryption, but it avoids
    leaving raw cookie JSON on disk and keeps the implementation dependency-free for the MVP.
    Keep the file under gitignored ``data/`` or another local-only path.
    """

    def __init__(self, path: str | os.PathLike[str], encryption_key: str | None = None):
        self.path = Path(path)
        self.encryption_key = encryption_key or ""

    def is_available(self) -> bool:
        return self.path.exists() and self.path.stat().st_size > 0

    def save_cookies(self, cookies: list[dict[str, Any]], username_hint: str = "") -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        bundle = StoredCookieBundle(
            cookies=cookies,
            saved_at=datetime.now(timezone.utc).isoformat(),
            username_hint=username_hint,
        )
        payload = json.dumps(
            {
                "version": 1,
                "saved_at": bundle.saved_at,
                "username_hint": bundle.username_hint,
                "cookies": bundle.cookies,
            },
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        if self.encryption_key:
            encoded = base64.urlsafe_b64encode(self._xor(payload)).decode("ascii")
            self.path.write_text(
                json.dumps({"version": 1, "encoding": "xor-base64", "payload": encoded}, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        else:
            self.path.write_bytes(payload)

    def load_cookies(self) -> list[dict[str, Any]]:
        if not self.is_available():
            return []
        raw = self.path.read_bytes()
        try:
            wrapper = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return []

        if isinstance(wrapper, dict) and wrapper.get("encoding") == "xor-base64":
            if not self.encryption_key:
                raise ValueError("Session cookie file is encoded; provide NAVER_SESSION_KEY to read it.")
            payload = base64.urlsafe_b64decode(str(wrapper.get("payload", "")).encode("ascii"))
            data = json.loads(self._xor(payload).decode("utf-8"))
        else:
            data = wrapper
        cookies = data.get("cookies", []) if isinstance(data, dict) else []
        return [cookie for cookie in cookies if isinstance(cookie, dict) and cookie.get("name")]

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()

    def _xor(self, data: bytes) -> bytes:
        digest = hashlib.sha256(self.encryption_key.encode("utf-8")).digest()
        return bytes(byte ^ digest[idx % len(digest)] for idx, byte in enumerate(data))
