from __future__ import annotations
import copy, json, os
from pathlib import Path
from typing import Any, Dict

DEFAULT_CONFIG_PATH = "/etc/lantern/client.conf"
DEFAULTS: Dict[str, Any] = {
    "version": 5,
    "hostName": os.uname().nodename,
    "paths": {
        "runtimeFolder": "/run/lantern",
        "localDataFolder": "/run/lantern/local",
        "outboxFolder": "/run/lantern/outbox",
        "updateFrequencyFile": "/run/lantern/config/updateFrequency",
    },
    "collection": {
        "defaultIntervalSeconds": 120,
        "minimumIntervalSeconds": 2,
        "maximumIntervalSeconds": 1800,
        "maintenanceModeFile": "/run/lantern/maintenanceMode",
    },
    "transport": {
        "mode": "rsyncSsh",
        "sshShortcut": f"mainSsh-{os.uname().nodename}",
        "remoteSnapshotFolder": "/run/lantern/snapshots",
        "keepPerHost": 10,
        "useLinkDest": True,
        "sshTimeoutSeconds": 10,
    },
}

def deep_merge(base, override):
    result = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(result.get(k), dict):
            result[k] = deep_merge(result[k], v)
        else:
            result[k] = v
    return result

def load_config(path: str | None = None) -> Dict[str, Any]:
    path = path or os.environ.get("LANTERN_CLIENT_CONFIG") or DEFAULT_CONFIG_PATH
    user = {}
    p = Path(path)
    if p.exists():
        user = json.loads(p.read_text(encoding="utf-8"))
    cfg = deep_merge(DEFAULTS, user)
    cfg["_configPath"] = str(p)
    return cfg

def p(config, key: str) -> Path:
    return Path(config["paths"][key])
