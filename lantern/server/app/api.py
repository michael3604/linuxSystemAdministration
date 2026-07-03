from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Dict

from flask import Blueprint, jsonify, request

from . import db
from .config import path_value
from .rules import effective_state, host_rule, numeric_state, service_rule
from .timeutil import iso_utc, now_ts

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
    return jsonify({"version": get_app_state().get("version", "unknown"), "ui": cfg.get("ui", {}), "hosts": cfg.get("hosts", {})})


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
                "timestamp": iso_utc(row["sourceTimestamp"]),
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
            "timestamp": iso_utc(r["sourceTimestamp"]),
            "value": r["value"],
            "unit": r["unit"],
            "text": r["text"],
            "defaultVisibleInGraph": bool(rule.get("defaultVisibleInGraph", False)) or state != "good",
        })
    services.sort(key=lambda x: (x["stateNumeric"], x["hostName"], x["serviceName"]), reverse=True)
    return jsonify({"services": services})


def _service_key(row: dict[str, Any] | Any) -> str:
    return f"{row['hostName']}/{row['serviceName']}/{row['sourceType']}"


def _service_point(cfg: dict[str, Any], row: dict[str, Any] | Any, ts: int, state: str | None = None) -> dict[str, Any]:
    """Return one graph point for the state that is valid at plot timestamp ``ts``.

    Staleness is time-dependent. A historical datapoint that is old *today* was
    not stale at the time it was written. Therefore service graphs must evaluate
    staleness at the plotted timestamp, not always relative to now.
    """
    source_ts = int(row["sourceTimestamp"])
    rule = service_rule(cfg, row["hostName"], row["serviceName"], row["sourceType"])
    if state is None:
        state = effective_state(row["status"], int(ts) - source_ts, float(rule.get("maxAgeSeconds", 90000)))
    return {
        "ts": int(ts),
        "sourceTs": source_ts,
        "status": state,
        "rawStatus": row["status"],
        "stateNumeric": numeric_state(state),
        "value": row["value"],
        "unit": row["unit"],
    }


def _service_expiry_ts(cfg: dict[str, Any], row: dict[str, Any] | Any) -> int | None:
    """Return the timestamp where this datapoint becomes stale, if applicable."""
    base_state = str(row["status"])
    if base_state in ("bad", "missing", "invalid"):
        return None
    rule = service_rule(cfg, row["hostName"], row["serviceName"], row["sourceType"])
    try:
        max_age = int(float(rule.get("maxAgeSeconds", 90000)))
    except Exception:
        return None
    if max_age < 0:
        return None
    # effective_state uses age > maxAgeSeconds, so the first stale second is +1.
    return int(row["sourceTimestamp"]) + max_age + 1


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
    rows_by_key: dict[str, list[Any]] = defaultdict(list)

    def ensure_group(row: dict[str, Any] | Any) -> dict[str, Any]:
        key = _service_key(row)
        rule = service_rule(cfg, row["hostName"], row["serviceName"], row["sourceType"])
        graph_min = rule.get("graphMin")
        graph_max = rule.get("graphMax")
        return groups.setdefault(key, {
            "key": key,
            "hostName": row["hostName"],
            "serviceName": row["serviceName"],
            "sourceType": row["sourceType"],
            "unit": row["unit"],
            "graphMin": graph_min,
            "graphMax": graph_max,
            "points": [],
        })

    for r in rows:
        rows_by_key[_service_key(r)].append(r)

    # Fallback: if a selected service has no serviceHistory row in or before the
    # range, use serviceCurrent. This also protects databases created by older
    # LANtern versions or manually edited state.
    for key in requested_keys:
        if not rows_by_key.get(key) and key in current_by_key:
            rows_by_key[key].append(current_by_key[key])

    for key, service_rows in rows_by_key.items():
        service_rows.sort(key=lambda r: int(r["sourceTimestamp"]))
        if not service_rows:
            continue
        g = ensure_group(service_rows[-1])
        if not g.get("unit"):
            # Prefer the latest non-empty unit, but do not require one.
            for r in reversed(service_rows):
                if r["unit"]:
                    g["unit"] = r["unit"]
                    break

        for idx, r in enumerate(service_rows):
            source_ts = int(r["sourceTimestamp"])
            next_ts = int(service_rows[idx + 1]["sourceTimestamp"]) if idx + 1 < len(service_rows) else server_now
            if next_ts < since:
                continue

            segment_start = max(source_ts, since)
            segment_end = min(next_ts, server_now)
            if segment_start > server_now:
                continue

            g["points"].append(_service_point(cfg, r, segment_start))

            expiry_ts = _service_expiry_ts(cfg, r)
            if expiry_ts is not None and segment_start < expiry_ts <= segment_end:
                rule = service_rule(cfg, r["hostName"], r["serviceName"], r["sourceType"])
                max_age = float(rule.get("maxAgeSeconds", 90000))
                before_expiry_state = effective_state(r["status"], segment_start - source_ts, max_age)
                expiry_state = effective_state(r["status"], expiry_ts - source_ts, max_age)
                if expiry_state != before_expiry_state:
                    g["points"].append(_service_point(cfg, r, expiry_ts, expiry_state))

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
