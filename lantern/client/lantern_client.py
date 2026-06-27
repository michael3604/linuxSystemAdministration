#!/usr/bin/env python3
from __future__ import annotations
import sys, time
from pathlib import Path

from config import load_config
from host_status import write_status
from snapshot import build_snapshot, cleanup_outbox
from transport import push_snapshot


def read_interval(config) -> int:
    coll = config['collection']
    default = int(coll.get('defaultIntervalSeconds', 120))
    minimum = int(coll.get('minimumIntervalSeconds', 2))
    maximum = int(coll.get('maximumIntervalSeconds', 1800))
    path = Path(config['paths'].get('updateFrequencyFile', '/run/lantern/config/updateFrequency'))
    try:
        value = int(path.read_text(encoding='utf-8').strip())
    except Exception:
        value = default
    return max(minimum, min(maximum, value))


def once(config) -> None:
    write_status(config)
    sid, snap = build_snapshot(config)
    push_snapshot(config, sid, snap)
    cleanup_outbox(config)


def daemon(config) -> None:
    while True:
        started = time.time()
        try:
            once(config)
        except Exception as exc:
            print(f'LANtern client error: {exc}', file=sys.stderr, flush=True)
        interval = read_interval(config)
        elapsed = time.time() - started
        time.sleep(max(1, interval - elapsed))


def main(argv: list[str]) -> int:
    mode = argv[1] if len(argv) > 1 else 'daemon'
    config = load_config()
    if mode == 'once':
        once(config); return 0
    if mode == 'daemon':
        daemon(config); return 0
    print('usage: lantern_client.py [once|daemon]', file=sys.stderr)
    return 2

if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
