from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Dict

from flask import Blueprint, jsonify, request

from . import db
from .config import path_value
from .rules import effective_state, host_rule, numeric_state, service_rule
from .timeutil import now_ts

api = Blueprint("api", __name__)


def get_app_state():
    from .lantern_server import APP_STATE
    return APP_STATE


def _conn():
    state = get_app_state()
    return db.connect(path_value(state["config"], "databasePath"))


@api.route("/api/config")
def config_api():
    cfg = get_app_state()["config"]
    return jsonify({"ui": cfg.get("ui", {}), "hosts": cfg.get("hosts", {})})


@api.route("/api/update-frequency", methods=["GET", "POST"])
def update_frequency():
    cfg = get_app_state()["config"]
    path = path_value(cfg, "updateFrequencyFile")
    if request.method == "POST":
        data = request.get_json(silent=True) or {}
        seconds = int(data.get("seconds", cfg.get("ui", {}).get("defaultUpdateFrequencySeconds", 120)))
        allowed = set(int(x) for x in cfg.get("ui", {}).get("allowedUpdateFrequencySeconds", [2, 10, 60, 120]))
        if seconds not in allowed:
            return jsonify({"ok": False, "error": "update frequency not allowed"}), 400
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{seconds}\n", encoding="utf-8")
        return jsonify({"ok": True, "seconds": seconds})
    try:
        seconds = int(path.read_text(encoding="utf-8").strip())
    except Exception:
        seconds = int(cfg.get("ui", {}).get("defaultUpdateFrequencySeconds", 120))
    return jsonify({"seconds": seconds})


@api.route("/api/hosts")
def hosts_current():
    cfg = get_app_state()["config"]
    now = now_ts()
    with _conn() as conn:
        rows = db.latest_hosts(conn)
    by_host = {r["hostName"]: r for r in rows}
    expected = set(cfg.get("hosts", {}).get("expected", [])) | set(by_host)
    ignored = set(cfg.get("hosts", {}).get("ignored", []))
    result = []
    for host in sorted(expected - ignored):
        row = by_host.get(host)
        rule = host_rule(cfg, host)
        max_age = float(rule.get("hostStatusMaxAgeSeconds", 180))
        if row is None:
            result.append({"hostName": host, "status": "missing", "ageSeconds": None, "statsPresent": False})
        else:
            age = now - int(row["sourceTimestamp"])
            status = "good" if age <= max_age else "stale"
            result.append({
                "hostName": host,
                "status": status,
                "ageSeconds": age,
                "statsPresent": True,
                "timestamp": row["rawTimestamp"],
                "cpuPercent": row["cpuPercent"],
                "ramPercent": row["ramPercent"],
                "ramAvailableMb": row["ramAvailableMb"],
                "cpuTempC": row["cpuTempC"],
                "maintenanceMode": bool(row["maintenanceMode"]),
            })
    return jsonify({"hosts": result})


@api.route("/api/host-series")
def host_series():
    cfg = get_app_state()["config"]
    range_seconds = int(float(request.args.get("rangeSeconds", cfg.get("ui", {}).get("defaultGraphRangeSeconds", 86400))))
    max_points = 1200
    bucket = max(1, range_seconds // max_points)
    since = now_ts() - range_seconds
    with _conn() as conn:
        rows = db.host_series(conn, since, bucket)
    hosts: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        hosts[r["hostName"]].append({
            "ts": int(r["bucketTs"]),
            "cpuPercent": r["cpuPercent"],
            "ramPercent": r["ramPercent"],
            "ramAvailableMb": r["ramAvailableMb"],
            "cpuTempC": r["cpuTempC"],
            "maintenanceMode": bool(r["maintenanceMode"]),
        })
    payload_hosts = []
    for host_name, points in hosts.items():
        rule = host_rule(cfg, host_name)
        payload_hosts.append({
            "hostName": host_name,
            "maxAgeSeconds": float(rule.get("hostStatusMaxAgeSeconds", 180)),
            "points": points,
        })
    return jsonify({"rangeSeconds": range_seconds, "bucketSeconds": bucket, "hosts": payload_hosts})


@api.route("/api/services")
def services_current():
    cfg = get_app_state()["config"]
    now = now_ts()
    with _conn() as conn:
        rows = db.current_services(conn)
    services = []
    for r in rows:
        rule = service_rule(cfg, r["hostName"], r["serviceName"], r["sourceType"])
        age = now - int(r["sourceTimestamp"])
        state = effective_state(r["status"], age, float(rule.get("maxAgeSeconds", 90000)))
        services.append({
            "key": f"{r['hostName']}/{r['serviceName']}/{r['sourceType']}",
            "hostName": r["hostName"],
            "serviceName": r["serviceName"],
            "sourceType": r["sourceType"],
            "status": state,
            "rawStatus": r["status"],
            "stateNumeric": numeric_state(state),
            "ageSeconds": age,
            "timestamp": r["rawTimestamp"],
            "value": r["value"],
            "unit": r["unit"],
            "text": r["text"],
            "defaultVisibleInGraph": bool(rule.get("defaultVisibleInGraph", False)) or state != "good",
        })
    services.sort(key=lambda x: (x["stateNumeric"], x["hostName"], x["serviceName"]), reverse=True)
    return jsonify({"services": services})


def _service_key(row: dict[str, Any] | Any) -> str:
    return f"{row['hostName']}/{row['serviceName']}/{row['sourceType']}"


def _service_point(cfg: dict[str, Any], row: dict[str, Any] | Any, ts: int | None = None) -> dict[str, Any]:
    """Return one graph point, recomputing stale state from the source timestamp.

    serviceHistory stores the raw state at ingest time. For sparse checks this is
    not enough for the graph: an 8-hour-old good datapoint should still be shown
    inside a 10-minute graph range, but a too-old datapoint should become stale
    according to its service maxAgeSeconds rule.
    """
    now = now_ts()
    source_ts = int(row["sourceTimestamp"])
    rule = service_rule(cfg, row["hostName"], row["serviceName"], row["sourceType"])
    state = effective_state(row["status"], now - source_ts, float(rule.get("maxAgeSeconds", 90000)))
    return {
        "ts": int(ts if ts is not None else source_ts),
        "sourceTs": source_ts,
        "status": state,
        "rawStatus": row["status"],
        "stateNumeric": numeric_state(state),
        "value": row["value"],
        "unit": row["unit"],
    }


@api.route("/api/service-series")
def service_series():
    cfg = get_app_state()["config"]
    range_seconds = int(float(request.args.get("rangeSeconds", cfg.get("ui", {}).get("defaultGraphRangeSeconds", 86400))))
    server_now = now_ts()
    since = server_now - range_seconds
    keys_arg = request.args.get("keys", "")
    keys = [k for k in keys_arg.split(",") if k]

    with _conn() as conn:
        current_rows = db.current_services(conn)
        current_by_key = {_service_key(r): r for r in current_rows}
        requested_keys = keys or sorted(current_by_key)
        rows = db.service_series(conn, since, requested_keys)

    groups: dict[str, dict[str, Any]] = {}

    def ensure_group(row: dict[str, Any] | Any) -> dict[str, Any]:
        key = _service_key(row)
        return groups.setdefault(key, {
            "key": key,
            "hostName": row["hostName"],
            "serviceName": row["serviceName"],
            "sourceType": row["sourceType"],
            "unit": row["unit"],
            "points": [],
        })

    for r in rows:
        g = ensure_group(r)
        # Clamp carry-forward seed rows to the graph start. This makes the API
        # explicitly return drawable data inside the requested range instead of
        # relying on browser-side reconstruction.
        plot_ts = since if int(r["sourceTimestamp"]) < since else int(r["sourceTimestamp"])
        g["points"].append(_service_point(cfg, r, plot_ts))

    # Fallback: if a selected service has no serviceHistory row in or before the
    # range, use serviceCurrent. This also protects databases created by older
    # LANtern versions or manually edited state.
    for key in requested_keys:
        row = current_by_key.get(key)
        if row is None:
            continue
        g = ensure_group(row)
        if not g["points"]:
            g["points"].append(_service_point(cfg, row, since))

    for g in groups.values():
        g["points"].sort(key=lambda p: (p["ts"], p.get("sourceTs", p["ts"])))
        # Collapse duplicate plot timestamps, keeping the newest source value.
        collapsed = {}
        for p in g["points"]:
            collapsed[int(p["ts"])] = p
        g["points"] = [collapsed[ts] for ts in sorted(collapsed)]

    return jsonify({
        "rangeSeconds": range_seconds,
        "rangeStart": since,
        "rangeEnd": server_now,
        "services": list(groups.values()),
    })
