from __future__ import annotations
import json, sys
from pathlib import Path

sys.path.insert(0, '/opt/lantern')
from server.app.config import load_config, path_value
from server.app.timeutil import parse_timestamp


def main() -> int:
    cfg = load_config()
    ok = True
    print(f"config: {cfg['_configPath']}")
    for key in ('snapshotFolder', 'successFilesFolder', 'stateFolder', 'databasePath', 'updateFrequencyFile'):
        path = path_value(cfg, key)
        exists = path.exists() if key != 'databasePath' else path.parent.exists()
        print(f"{key}: {path} {'OK' if exists else 'MISSING'}")
        ok = ok and exists
    snap = path_value(cfg, 'snapshotFolder')
    if snap.exists():
        complete = list(snap.glob('*/*'))
        print(f"snapshot entries: {len(complete)}")
    succ = path_value(cfg, 'successFilesFolder')
    if succ.exists():
        count = 0; bad = 0
        for f in succ.glob('*/*.success'):
            count += 1
            try:
                text = f.read_text().strip().splitlines()[0]
            except Exception:
                text = ''
            if parse_timestamp(text) is None:
                bad += 1
        print(f"success files: {count}, invalid timestamps: {bad}")
        ok = ok and bad == 0
    return 0 if ok else 1

if __name__ == '__main__':
    raise SystemExit(main())
