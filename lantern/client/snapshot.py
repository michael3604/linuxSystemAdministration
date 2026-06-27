from __future__ import annotations
import shutil
from pathlib import Path
from typing import Dict, Any

from timeutil import snapshot_id


def build_snapshot(config: Dict[str, Any]) -> tuple[str, Path]:
    host = config['hostName']
    local = Path(config['paths']['localDataFolder'])
    outbox = Path(config['paths']['outboxFolder'])
    sid = snapshot_id()
    dest = outbox / sid
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    for src in sorted(local.glob('*.json')):
        shutil.copy2(src, dest / src.name)
    return sid, dest


def cleanup_outbox(config: Dict[str, Any], keep: int = 3) -> None:
    outbox = Path(config['paths']['outboxFolder'])
    if not outbox.exists():
        return
    dirs = sorted([p for p in outbox.iterdir() if p.is_dir()], key=lambda p: p.name, reverse=True)
    for p in dirs[keep:]:
        shutil.rmtree(p, ignore_errors=True)
