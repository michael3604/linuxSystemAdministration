from __future__ import annotations

import threading
import time
from pathlib import Path

from flask import Flask, render_template

from . import db
from .api import api
from .config import load_config, path_value
from .ingest import ingest_once

APP_STATE = {"config": None}


def create_app() -> Flask:
    app = Flask(__name__, static_folder="static", template_folder="templates")
    config = load_config()
    APP_STATE["config"] = config

    db_path = path_value(config, "databasePath")
    with db.connect(db_path) as conn:
        db.init_db(conn)

    app.register_blueprint(api)

    @app.route("/")
    def index():
        return render_template("index.html")

    start_ingest_thread(config)
    return app


def ingest_loop(config):
    interval = max(1, int(config.get("ingest", {}).get("intervalSeconds", 2)))
    db_path = path_value(config, "databasePath")
    while True:
        try:
            with db.connect(db_path) as conn:
                db.init_db(conn)
                ingest_once(conn, config)
        except Exception as exc:
            print(f"LANtern ingest error: {exc}", flush=True)
        time.sleep(interval)


def start_ingest_thread(config):
    thread = threading.Thread(target=ingest_loop, args=(config,), daemon=True)
    thread.start()


app = create_app()
