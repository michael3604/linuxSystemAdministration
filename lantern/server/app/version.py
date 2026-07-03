from __future__ import annotations

import os
from pathlib import Path


COMPILED_VERSION = "0.5.12"


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value or value.lower() == "unknown":
        return None
    return value


def get_version() -> str:
    env_version = _clean(os.environ.get("LANTERN_VERSION"))
    if env_version:
        return env_version

    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "VERSION"
        if candidate.exists():
            try:
                file_version = _clean(candidate.read_text(encoding="utf-8"))
            except OSError:
                file_version = None
            if file_version:
                return file_version

    return COMPILED_VERSION
