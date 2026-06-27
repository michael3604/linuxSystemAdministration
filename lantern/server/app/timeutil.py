from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


def now_ts() -> int:
    return int(datetime.now(timezone.utc).timestamp())


def now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SUTC")


def parse_timestamp(value: object) -> Optional[int]:
    if value is None:
        return None
    try:
        text = str(value).strip().splitlines()[0].strip()
        if not text:
            return None
        if text.endswith(" UTC"):
            text = text[:-4] + "+00:00"
        elif text.endswith("UTC"):
            text = text[:-3] + "+00:00"
        elif text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except Exception:
        return None


def format_age(seconds: Optional[float]) -> str:
    if seconds is None:
        return "—"
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds} s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes} min"
    hours = minutes // 60
    if hours < 48:
        return f"{hours} h"
    days = hours // 24
    return f"{days} d"
