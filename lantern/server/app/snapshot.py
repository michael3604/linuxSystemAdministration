from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Iterable, List


def is_complete_snapshot(path: Path) -> bool:
    return path.is_dir() and not path.name.endswith(".inWork") and not path.name.startswith(".")


def list_hosts(snapshot_root: Path) -> list[str]:
    if not snapshot_root.exists():
        return []
    return sorted([p.name for p in snapshot_root.iterdir() if p.is_dir() and not p.name.startswith("_")])


def list_completed_snapshots(snapshot_root: Path, host: str) -> list[Path]:
    host_dir = snapshot_root / host
    if not host_dir.exists():
        return []
    return sorted([p for p in host_dir.iterdir() if is_complete_snapshot(p)], key=lambda p: p.name)


def snapshots_after(snapshots: list[Path], last_id: str | None) -> list[Path]:
    if not last_id:
        return snapshots
    return [p for p in snapshots if p.name > last_id]


def cleanup_snapshots(snapshot_root: Path, host: str, keep: int, delete_inwork_older_than: int) -> None:
    host_dir = snapshot_root / host
    if not host_dir.exists():
        return
    now = time.time()
    for p in host_dir.iterdir():
        if p.is_dir() and p.name.endswith(".inWork"):
            try:
                age = now - p.stat().st_mtime
                if age > delete_inwork_older_than:
                    shutil.rmtree(p)
            except FileNotFoundError:
                pass
    complete = sorted([p for p in host_dir.iterdir() if is_complete_snapshot(p)], key=lambda p: p.name, reverse=True)
    for old in complete[max(0, keep):]:
        shutil.rmtree(old, ignore_errors=True)
