from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from . import db
from .config import path_value
from .rules import normalize_status, numeric_state, service_rule
from .snapshot import cleanup_snapshots, list_completed_snapshots, list_hosts, snapshots_after
from .timeutil import now_ts, parse_timestamp


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _service_name_from_path(path: Path) -> str:
    return path.stem


def ingest_host_snapshot(conn, config: Dict[str, Any], host: str, snap: Path, ts_now: int) -> None:
    status_path = snap / "status.json"
    status = _read_json(status_path)
    if status:
        raw_ts = str(status.get("timestamp", "")).strip()
        source_ts = parse_timestamp(raw_ts)
        if source_ts is not None:
            row = {
                "hostName": str(status.get("hostName") or status.get("hostname") or host),
                "sourceTimestamp": source_ts,
                "rawTimestamp": raw_ts,
                "cpuPercent": status.get("cpuPercent", status.get("cpu_percent")),
                "ramPercent": status.get("ramPercent", status.get("ram_percent")),
                "ramAvailableMb": status.get("ramAvailableMb"),
                "cpuTempC": status.get("cpuTempC", status.get("cpu_temp_c")),
                "maintenanceMode": bool(status.get("maintenanceMode", status.get("maintenance_mode", False))),
                "ingestedAt": ts_now,
                "snapshotId": snap.name,
            }
            db.insert_host_status(conn, row)

    for service_path in sorted(snap.glob("*.json")):
        if service_path.name == "status.json":
            continue
        payload = _read_json(service_path)
        service = _service_name_from_path(service_path)
        if not payload:
            raw_ts = str(ts_now)
            row = {
                "hostName": host,
                "serviceName": service,
                "sourceType": "serviceJson",
                "sourceTimestamp": ts_now,
                "rawTimestamp": raw_ts,
                "status": "invalid",
                "stateNumeric": numeric_state("invalid"),
                "value": None,
                "unit": None,
                "text": "invalid JSON",
                "ingestedAt": ts_now,
                "snapshotId": snap.name,
            }
            db.upsert_service(conn, row)
            continue
        raw_ts = str(payload.get("timestamp", "")).strip()
        source_ts = parse_timestamp(raw_ts)
        state = normalize_status(payload.get("status"), config)
        if source_ts is None:
            source_ts = ts_now
            raw_ts = raw_ts or str(ts_now)
            state = "invalid"
        value = payload.get("value")
        try:
            value = None if value is None or value == "" else float(value)
        except Exception:
            value = None
        row = {
            "hostName": host,
            "serviceName": service,
            "sourceType": "serviceJson",
            "sourceTimestamp": source_ts,
            "rawTimestamp": raw_ts,
            "status": state,
            "stateNumeric": numeric_state(state),
            "value": value,
            "unit": payload.get("unit"),
            "text": payload.get("text") or payload.get("message") or payload.get("comment"),
            "ingestedAt": ts_now,
            "snapshotId": snap.name,
        }
        db.upsert_service(conn, row)


def ingest_snapshots(conn, config: Dict[str, Any]) -> None:
    root = path_value(config, "snapshotFolder")
    root.mkdir(parents=True, exist_ok=True)
    ignored = set(config.get("hosts", {}).get("ignored", []))
    hosts = set(list_hosts(root)) | set(config.get("hosts", {}).get("expected", []))
    keep = int(config.get("snapshots", {}).get("keepPerHost", 10))
    stale_inwork = int(config.get("snapshots", {}).get("deleteInWorkOlderThanSeconds", 300))
    ts_now = now_ts()
    for host in sorted(hosts - ignored):
        completed = list_completed_snapshots(root, host)
        last = db.get_last_snapshot(conn, host)
        for snap in snapshots_after(completed, last):
            ingest_host_snapshot(conn, config, host, snap, ts_now)
            db.set_last_snapshot(conn, host, snap.name, ts_now)
        cleanup_snapshots(root, host, keep, stale_inwork)
    conn.commit()


def ingest_success_files(conn, config: Dict[str, Any]) -> None:
    root = path_value(config, "successFilesFolder")
    if not root.exists():
        return
    ts_now = now_ts()
    for host_dir in sorted([p for p in root.iterdir() if p.is_dir()]):
        host = host_dir.name
        if host in set(config.get("hosts", {}).get("ignored", [])):
            continue
        for path in sorted(host_dir.glob("*.success")):
            service = path.stem
            try:
                raw_ts = path.read_text(encoding="utf-8").strip().splitlines()[0].strip()
            except Exception:
                raw_ts = ""
            source_ts = parse_timestamp(raw_ts)
            if source_ts is None:
                state = "invalid"
                source_ts = ts_now
            else:
                rule = service_rule(config, host, service, "successFile")
                max_age = float(rule.get("maxAgeSeconds", 90000))
                state = "good" if (ts_now - source_ts) <= max_age else "stale"
            row = {
                "hostName": host,
                "serviceName": service,
                "sourceType": "successFile",
                "sourceTimestamp": source_ts,
                "rawTimestamp": raw_ts,
                "status": state,
                "stateNumeric": numeric_state(state),
                "value": None,
                "unit": None,
                "text": None,
                "ingestedAt": ts_now,
                "snapshotId": None,
            }
            db.upsert_service(conn, row)
    conn.commit()


def ingest_once(conn, config: Dict[str, Any]) -> None:
    ingest_snapshots(conn, config)
    ingest_success_files(conn, config)
