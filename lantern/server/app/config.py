from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any, Dict

DEFAULT_CONFIG_PATH = "/etc/lantern/server.conf"

DEFAULTS: Dict[str, Any] = {
    "version": 5,
    "paths": {
        "snapshotFolder": "/run/lantern/snapshots",
        "successFilesFolder": "/var/lib/success",
        "stateFolder": "/var/lib/lantern/state",
        "databasePath": "/var/lib/lantern/state/lantern.sqlite3",
        "updateFrequencyFile": "/run/lantern/config/updateFrequency",
    },
    "server": {"listenHost": "0.0.0.0", "listenPort": 8010},
    "ingest": {"intervalSeconds": 2, "retentionDays": 30},
    "snapshots": {"keepPerHost": 10, "deleteInWorkOlderThanSeconds": 300},
    "ui": {
        "defaultUpdateFrequencySeconds": 120,
        "allowedUpdateFrequencySeconds": [2, 10, 60, 120],
        "defaultGraphRangeSeconds": 86400,
        "graphRanges": [
            {"label": "10 min", "seconds": 600},
            {"label": "3 h", "seconds": 10800},
            {"label": "24 h", "seconds": 86400},
            {"label": "7 d", "seconds": 604800},
        ],
    },
    "hosts": {"expected": [], "ignored": [], "defaults": {"hostStatusMaxAgeSeconds": 180}, "perHost": {}},
    "statusValues": {
        "good": ["good", "ok", "available", "healthy", "up", "mounted", "true", "1"],
        "bad": ["bad", "error", "failed", "unavailable", "down", "missing", "false", "0"],
        "unknown": ["unknown", "skipped", "maintenance", "n/a"],
    },
    "services": {"defaults": {"maxAgeSeconds": 90000, "defaultVisibleInGraph": False}, "perService": {}},
    "successFiles": {"defaults": {"maxAgeSeconds": 90000, "defaultVisibleInGraph": True}, "perService": {}},
    "updateFrequencyManager": {
        "enabled": False,
        "checkIntervalSeconds": 5,
        "resetAfterSeconds": 1800,
        "resetToSeconds": 120,
        "clients": {},
    },
}


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: str | None = None) -> Dict[str, Any]:
    path = path or os.environ.get("LANTERN_SERVER_CONFIG") or DEFAULT_CONFIG_PATH
    cfg_path = Path(path)
    user = {}
    if cfg_path.exists():
        with cfg_path.open("r", encoding="utf-8") as f:
            user = json.load(f)
    cfg = deep_merge(DEFAULTS, user)
    cfg["_configPath"] = str(cfg_path)
    return cfg


def path_value(config: Dict[str, Any], name: str) -> Path:
    return Path(config["paths"][name])
