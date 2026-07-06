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
    # The client may create its own host directory, but it must not create the
    # shared snapshot root. The server/tmpfiles owns the snapshot root and its
    # 1777 permissions.
    cmd = (
        f"test -d {shlex.quote(remote_root.rstrip('/'))} || exit 66; "
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
    remote_cmd(
        ssh,
        # Do not create or chmod remote_root here. It is a shared inbox owned by
        # the server boot/install process and should already exist with 1777
        # permissions. Creating it from the first client can leave it as 0755.
        f"test -d {shlex.quote(remote_root)} || "
        f"(echo 'LANtern remote snapshot root missing: {shlex.quote(remote_root)}' >&2; exit 66); "
        f"mkdir -p {shlex.quote(remote_host_dir)} && "
        f"rm -rf {shlex.quote(remote_inwork)}",
    )
    rsync = ['rsync', '-a', '--delete']
    if tr.get('useLinkDest', True):
        prev = find_remote_previous(ssh, remote_root, host)
        if prev:
            rsync.append(f"--link-dest={remote_host_dir}/{prev}")
    rsync.extend([str(snapshot_path) + '/', f"{ssh}:{remote_inwork}/"])
    run(rsync, check=True)
    remote_cmd(ssh, f"rm -rf {shlex.quote(remote_final)} && mv {shlex.quote(remote_inwork)} {shlex.quote(remote_final)}")
    cleanup_remote(ssh, remote_root, host, keep)


def _latest_local_snapshot(host_dir: Path) -> Path | None:
    if not host_dir.exists():
        return None
    candidates = sorted(
        [p for p in host_dir.iterdir() if p.is_dir() and not p.name.endswith('.inWork')],
        key=lambda p: p.name,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _copy_file_replace(src: Path, dst: Path) -> None:
    """Copy src to dst without modifying an existing hardlink target in place."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(f'.{dst.name}.{os.getpid()}.tmp')
    if tmp.exists():
        tmp.unlink()
    shutil.copy2(src, tmp)
    os.replace(tmp, dst)


def _remove_paths_not_in_source(source: Path, dest: Path) -> None:
    if not dest.exists():
        return
    for child in sorted(dest.rglob('*'), key=lambda p: len(p.parts), reverse=True):
        rel = child.relative_to(dest)
        if not (source / rel).exists():
            if child.is_dir():
                try:
                    child.rmdir()
                except OSError:
                    pass
            else:
                child.unlink(missing_ok=True)


def _overlay_snapshot(source: Path, dest: Path) -> None:
    for src in sorted(source.rglob('*')):
        rel = src.relative_to(source)
        target = dest / rel
        if src.is_dir():
            target.mkdir(parents=True, exist_ok=True)
        elif src.is_file():
            _copy_file_replace(src, target)


def cleanup_local(root: Path, host: str, keep: int) -> None:
    host_dir = root / host
    if not host_dir.exists():
        return
    for p in host_dir.iterdir():
        if p.is_dir() and p.name.endswith('.inWork'):
            shutil.rmtree(p, ignore_errors=True)
    dirs = sorted([p for p in host_dir.iterdir() if p.is_dir()], key=lambda p: p.name, reverse=True)
    for p in dirs[keep:]:
        shutil.rmtree(p, ignore_errors=True)


def push_local(config: Dict[str, Any], snapshot_id: str, snapshot_path: Path) -> None:
    host = config['hostName']
    tr = config.get('transport', {})
    root = Path(tr.get('remoteSnapshotFolder', '/run/lantern/snapshots'))
    host_dir = root / host
    inwork = host_dir / f'{snapshot_id}.inWork'
    final = host_dir / snapshot_id
    keep = int(tr.get('keepPerHost', 10))

    if not root.exists():
        raise FileNotFoundError(
            f"LANtern local snapshot root missing: {root}. "
            "Create it on the server side with mode 1777 before starting clients."
        )
    if not root.is_dir():
        raise NotADirectoryError(f"LANtern local snapshot root is not a directory: {root}")
    # Do not create or chmod root here. The server boot/install process owns the
    # shared snapshot root and its 1777 permissions. The client only creates its
    # own host subdirectory.
    host_dir.mkdir(parents=True, exist_ok=True)
    if inwork.exists():
        shutil.rmtree(inwork)

    # If link-dest is requested, hardlink the previous completed snapshot inside
    # the destination filesystem first, then replace changed files from the new
    # source snapshot. Do not hardlink from /run/outbox to /mnt/... because that
    # can cross filesystem boundaries and fail with EXDEV. Also do not overwrite
    # hardlinked files in place, because that would mutate the previous snapshot.
    previous = _latest_local_snapshot(host_dir) if tr.get('useLinkDest', True) else None
    if previous:
        shutil.copytree(previous, inwork, copy_function=os.link)
        _remove_paths_not_in_source(snapshot_path, inwork)
    else:
        inwork.mkdir(parents=True, exist_ok=True)

    _overlay_snapshot(snapshot_path, inwork)

    if final.exists():
        shutil.rmtree(final)
    os.replace(inwork, final)
    cleanup_local(root, host, keep)


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
