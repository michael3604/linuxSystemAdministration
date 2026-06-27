from __future__ import annotations

from waitress import serve

from .config import load_config
from .lantern_server import app

cfg = load_config()
server = cfg.get("server", {})
serve(app, host=server.get("listenHost", "0.0.0.0"), port=int(server.get("listenPort", 8010)))
