from __future__ import annotations
import sys

sys.path.insert(0, '/opt/lantern')
from server.app.config import load_config, path_value
from server.app import db


def main() -> int:
    cfg = load_config()
    with db.connect(path_value(cfg, 'databasePath')) as conn:
        db.init_db(conn)
        stats = db.db_stats(conn)
        for k, v in stats.items():
            print(f"{k}: {v}")
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
