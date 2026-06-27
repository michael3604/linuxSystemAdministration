from __future__ import annotations

import subprocess
import time
from pathlib import Path

from .config import load_config, path_value


def read_seconds(path: Path, default: int) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except Exception:
        return default


def push_to_client(ssh_shortcut: str, remote_file: str, seconds: int) -> None:
    cmd = (
        "set -e; "
        f"mkdir -p {str(Path(remote_file).parent)}; "
        f"printf '%s\\n' {seconds!s} > {remote_file}"
    )
    subprocess.run(["ssh", ssh_shortcut, cmd], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> int:
    cfg = load_config()
    mgr = cfg.get("updateFrequencyManager", {})
    path = path_value(cfg, "updateFrequencyFile")
    default = int(mgr.get("resetToSeconds", 120))
    check_interval = int(mgr.get("checkIntervalSeconds", 5))
    reset_after = int(mgr.get("resetAfterSeconds", 1800))
    remote_file = str(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(f"{default}\n", encoding="utf-8")
    while True:
        seconds = read_seconds(path, default)
        try:
            age = time.time() - path.stat().st_mtime
        except FileNotFoundError:
            age = reset_after + 1
        if age > reset_after and seconds != default:
            seconds = default
            path.write_text(f"{seconds}\n", encoding="utf-8")
        for client in mgr.get("clients", {}).values():
            shortcut = client.get("sshShortcut")
            if shortcut:
                push_to_client(shortcut, remote_file, seconds)
        time.sleep(check_interval)


if __name__ == "__main__":
    raise SystemExit(main())
