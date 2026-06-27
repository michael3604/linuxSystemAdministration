from __future__ import annotations
import os, shlex, shutil, subprocess
from pathlib import Path
from typing import Dict, Any


def run(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=check, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)


def remote_cmd(ssh: str, command: str) -> subprocess.CompletedProcess:
    return run(['ssh', ssh, command], check=True)


def find_remote_previous(ssh: str, remote_root: str, host: str) -> str | None:
    host_dir = f"{remote_root.rstrip('/')}/{host}"
    cmd = (
        f"mkdir -p {shlex.quote(host_dir)}; "
        f"find {shlex.quote(host_dir)} -mindepth 1 -maxdepth 1 -type d ! -name '*.inWork' -printf '%f\\n' "
        "| sort | tail -n 1"
    )
    try:
        res = remote_cmd(ssh, cmd)
        val = res.stdout.strip()
        return val or None
    except Exception:
        return None


def cleanup_remote(ssh: str, remote_root: str, host: str, keep: int) -> None:
    host_dir = f"{remote_root.rstrip('/')}/{host}"
    cmd = (
        f"cd {shlex.quote(host_dir)} 2>/dev/null || exit 0; "
        "find . -mindepth 1 -maxdepth 1 -type d -name '*.inWork' -mmin +5 -exec rm -rf {} +; "
        "find . -mindepth 1 -maxdepth 1 -type d ! -name '*.inWork' -printf '%f\\n' "
        "| sort -r | tail -n +$((" + str(keep) + "+1)) "
        "| while read d; do [ -n \"$d\" ] && rm -rf \"$d\"; done"
    )
    try:
        remote_cmd(ssh, cmd)
    except Exception:
        pass


def push_rsync_ssh(config: Dict[str, Any], snapshot_id: str, snapshot_path: Path) -> None:
    host = config['hostName']
    tr = config['transport']
    ssh = tr['sshShortcut']
    remote_root = tr.get('remoteSnapshotFolder', '/run/lantern/snapshots').rstrip('/')
    keep = int(tr.get('keepPerHost', 10))
    remote_host_dir = f"{remote_root}/{host}"
    remote_inwork = f"{remote_host_dir}/{snapshot_id}.inWork"
    remote_final = f"{remote_host_dir}/{snapshot_id}"
    remote_cmd(ssh, f"mkdir -p {shlex.quote(remote_host_dir)} && rm -rf {shlex.quote(remote_inwork)}")
    rsync = ['rsync', '-a', '--delete']
    if tr.get('useLinkDest', True):
        prev = find_remote_previous(ssh, remote_root, host)
        if prev:
            rsync.append(f"--link-dest={remote_host_dir}/{prev}")
    rsync.extend([str(snapshot_path) + '/', f"{ssh}:{remote_inwork}/"])
    run(rsync, check=True)
    remote_cmd(ssh, f"rm -rf {shlex.quote(remote_final)} && mv {shlex.quote(remote_inwork)} {shlex.quote(remote_final)}")
    cleanup_remote(ssh, remote_root, host, keep)


def push_local(config: Dict[str, Any], snapshot_id: str, snapshot_path: Path) -> None:
    host = config['hostName']
    root = Path(config['transport'].get('remoteSnapshotFolder', '/run/lantern/snapshots'))
    host_dir = root / host
    inwork = host_dir / f'{snapshot_id}.inWork'
    final = host_dir / snapshot_id
    host_dir.mkdir(parents=True, exist_ok=True)
    if inwork.exists(): shutil.rmtree(inwork)
    shutil.copytree(snapshot_path, inwork, copy_function=os.link if config['transport'].get('useLinkDest', False) else shutil.copy2)
    if final.exists(): shutil.rmtree(final)
    inwork.rename(final)


def push_snapshot(config: Dict[str, Any], snapshot_id: str, snapshot_path: Path) -> None:
    mode = config.get('transport', {}).get('mode', 'rsyncSsh')
    if mode == 'none':
        return
    if mode == 'local':
        push_local(config, snapshot_id, snapshot_path)
    elif mode == 'rsyncSsh':
        push_rsync_ssh(config, snapshot_id, snapshot_path)
    else:
        raise ValueError(f'unknown transport mode: {mode}')
