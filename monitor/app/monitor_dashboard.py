#!/usr/bin/env python3

import json
import math
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template, request


CONFIG_PATH = "/var/lib/monitor-dashboard/config/monitor.conf"

app = Flask(__name__)


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def config_section(config, section_name):
    value = config.get(section_name, {})
    return value if isinstance(value, dict) else {}


def path_config(config):
    return config_section(config, "paths")


def input_config(config):
    return config_section(config, "inputs")


def host_config(config):
    return config_section(config, "hosts")


def ui_config(config):
    return config_section(config, "ui")


def ingest_config(config):
    return config_section(config, "ingest")


def server_config(config):
    return config_section(config, "server")


def state_dir(config):
    return Path(path_config(config).get("state_dir", "/var/lib/monitor-dashboard/state"))


def db_path(config):
    return Path(config.get("db_path") or state_dir(config) / "monitor.sqlite3")


def monitor_root(config):
    return Path(path_config(config).get("monitor_root", "/mnt/monitor"))


def success_root(config):
    return Path(path_config(config).get("success_root", "/mnt/successfiles"))


def input_root(config, input_name, fallback):
    inputs = input_config(config)
    item = inputs.get(input_name, {}) if isinstance(inputs.get(input_name, {}), dict) else {}
    root = item.get("root")
    return Path(root) if root else fallback


def input_filename(config, input_name, default):
    inputs = input_config(config)
    item = inputs.get(input_name, {}) if isinstance(inputs.get(input_name, {}), dict) else {}
    return item.get("filename", default)


def input_globs(config, input_name, default_globs):
    inputs = input_config(config)
    item = inputs.get(input_name, {}) if isinstance(inputs.get(input_name, {}), dict) else {}
    if "globs" in item and isinstance(item["globs"], list):
        return [str(v) for v in item["globs"]]
    if "glob" in item:
        return [str(item["glob"])]
    return list(default_globs)


def expected_hosts(config):
    hosts = host_config(config).get("expected", [])
    return {str(h) for h in hosts} if isinstance(hosts, list) else set()


def ignored_hosts(config):
    hosts = host_config(config).get("ignored", [])
    return {str(h) for h in hosts} if isinstance(hosts, list) else set()


def db_connect():
    config = load_config()
    db_file = db_path(config)
    db_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_file), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def init_db():
    config = load_config()
    db_path(config).parent.mkdir(parents=True, exist_ok=True)

    with db_connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS system_stats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                host TEXT NOT NULL,
                source_ts INTEGER NOT NULL,
                sample_ts INTEGER NOT NULL,
                cpu_percent REAL,
                ram_percent REAL,
                cpu_temp_c REAL,
                maintenance_mode INTEGER,
                UNIQUE(host, source_ts)
            );

            CREATE INDEX IF NOT EXISTS idx_system_stats_host_ts
            ON system_stats(host, source_ts);

            CREATE TABLE IF NOT EXISTS host_status (
                host TEXT PRIMARY KEY,
                seen_ts INTEGER NOT NULL,
                stats_present INTEGER NOT NULL,
                error TEXT,
                source_ts INTEGER
            );

            CREATE TABLE IF NOT EXISTS status_files (
                host TEXT NOT NULL,
                function TEXT NOT NULL,
                relpath TEXT NOT NULL,
                content TEXT,
                state TEXT NOT NULL,
                ok INTEGER NOT NULL,
                seen_ts INTEGER NOT NULL,
                PRIMARY KEY(host, function)
            );

            CREATE TABLE IF NOT EXISTS heartbeat_files (
                host TEXT NOT NULL,
                function TEXT NOT NULL,
                relpath TEXT NOT NULL,
                content TEXT,
                timestamp_ts INTEGER,
                age_seconds REAL,
                max_age_seconds REAL NOT NULL,
                ok INTEGER NOT NULL,
                error TEXT,
                seen_ts INTEGER NOT NULL,
                PRIMARY KEY(host, function)
            );

            CREATE TABLE IF NOT EXISTS success_files (
                host TEXT NOT NULL,
                script TEXT NOT NULL,
                relpath TEXT NOT NULL,
                content TEXT,
                timestamp_ts INTEGER,
                age_seconds REAL,
                max_age_seconds REAL NOT NULL,
                ok INTEGER NOT NULL,
                error TEXT,
                seen_ts INTEGER NOT NULL,
                PRIMARY KEY(host, script)
            );
        """)


def parse_timestamp(value):
    if value is None:
        return None

    try:
        text = str(value).strip().splitlines()[0].strip()

        # Accept common UTC notations:
        # 2026-06-22T13:35:34Z
        # 2026-06-22T13:35:34+00:00
        # 2026-06-22T13:35:34 UTC
        # 2026-06-22T13:35:34UTC
        if text.endswith(" UTC"):
            text = text[:-4] + "+00:00"
        elif text.endswith("UTC"):
            text = text[:-3] + "+00:00"
        elif text.endswith("Z"):
            text = text[:-1] + "+00:00"

        dt = datetime.fromisoformat(text)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return int(dt.timestamp())
    except Exception:
        return None

def safe_float(value):
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def bool_to_int(value):
    if isinstance(value, bool):
        return 1 if value else 0

    if isinstance(value, str):
        return 1 if value.strip().lower() in ("1", "true", "yes", "on") else 0

    return 1 if value else 0


def looks_like_rule(value):
    if not isinstance(value, dict):
        return False

    rule_keys = {"good", "bad", "max_age_seconds", "unknown_is_ok"}
    return any(key in value for key in rule_keys)


def merged_rule(config_rules, host, name, default_rule):
    result = dict(default_rule)

    if not isinstance(config_rules, dict):
        return result

    global_rules = config_rules.get("_default", {})
    host_rules = config_rules.get(host, {})

    if looks_like_rule(global_rules):
        result.update(global_rules)
    elif isinstance(global_rules, dict):
        if isinstance(global_rules.get("_default"), dict):
            result.update(global_rules["_default"])
        if isinstance(global_rules.get(name), dict):
            result.update(global_rules[name])

    if looks_like_rule(host_rules):
        result.update(host_rules)
    elif isinstance(host_rules, dict):
        if isinstance(host_rules.get("_default"), dict):
            result.update(host_rules["_default"])
        if isinstance(host_rules.get(name), dict):
            result.update(host_rules[name])

    return result


def status_rule(config, host, function):
    return merged_rule(
        config.get("status_rules", {}),
        host,
        function,
        {
            "good": ["ok", "green", "true", "1"],
            "bad": ["bad", "red", "error", "fail", "failed", "false", "0"],
            "unknown_is_ok": False,
        },
    )


def heartbeat_rule(config, host, function):
    return merged_rule(
        config.get("heartbeat_rules", {}),
        host,
        function,
        {"max_age_seconds": 180},
    )


def success_rule(config, host, script):
    return merged_rule(
        config.get("success_file_rules", {}),
        host,
        script,
        {"max_age_seconds": 90000},
    )


def evaluate_status_content(config, host, function, content):
    rule = status_rule(config, host, function)

    good_values = {str(v).strip().lower() for v in rule.get("good", [])}
    bad_values = {str(v).strip().lower() for v in rule.get("bad", [])}
    unknown_is_ok = bool(rule.get("unknown_is_ok", False))

    normalized = str(content).strip().lower()

    if normalized in good_values:
        return "good", True

    if normalized in bad_values:
        return "bad", False

    return "unknown", unknown_is_ok


def read_text_file(path):
    return path.read_text(encoding="utf-8", errors="replace").strip()


def strip_suffix_case_insensitive(filename, suffix):
    if filename.lower().endswith(suffix.lower()):
        return filename[: -len(suffix)]
    return filename


def function_from_globs(path, suffixes):
    name = path.name
    for suffix in suffixes:
        stripped = strip_suffix_case_insensitive(name, suffix)
        if stripped != name:
            return stripped
    return path.stem


def list_host_dirs(root):
    if not root.exists():
        return {}

    return {
        p.name: p
        for p in root.iterdir()
        if p.is_dir()
    }


def scan_hosts_for_system_stats(config):
    root = input_root(config, "system_stats", monitor_root(config))
    dirs = list_host_dirs(root)
    all_hosts = set(dirs.keys()) | expected_hosts(config)
    ignore = ignored_hosts(config)
    return root, dirs, sorted(h for h in all_hosts if h not in ignore)


def ingest_once():
    config = load_config()
    now = int(time.time())

    with db_connect() as conn:
        scan_system_stats(conn, config, now)
        scan_status_files(conn, config, now)
        scan_heartbeat_files(conn, config, now)
        scan_success_files(conn, config, now)
        prune_old_data(conn, config, now)


def scan_system_stats(conn, config, now):
    root, dirs, hosts = scan_hosts_for_system_stats(config)
    filename = input_filename(config, "system_stats", "systemStats.json")

    if not root.exists():
        print(f"system_stats root does not exist: {root}", flush=True)

    for host in hosts:
        host_dir = dirs.get(host)
        stats_path = host_dir / filename if host_dir else root / host / filename

        error = None
        source_ts = None
        stats_present = 1 if stats_path.exists() else 0

        if stats_path.exists():
            try:
                with open(stats_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                source_ts = parse_timestamp(data.get("timestamp"))

                if source_ts is None:
                    raise ValueError("missing or invalid timestamp")

                conn.execute(
                    """
                    INSERT INTO system_stats (
                        host,
                        source_ts,
                        sample_ts,
                        cpu_percent,
                        ram_percent,
                        cpu_temp_c,
                        maintenance_mode
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(host, source_ts) DO UPDATE SET
                        sample_ts = excluded.sample_ts,
                        cpu_percent = excluded.cpu_percent,
                        ram_percent = excluded.ram_percent,
                        cpu_temp_c = excluded.cpu_temp_c,
                        maintenance_mode = excluded.maintenance_mode
                    """,
                    (
                        host,
                        source_ts,
                        now,
                        safe_float(data.get("cpu_percent")),
                        safe_float(data.get("ram_percent")),
                        safe_float(data.get("cpu_temp_c")),
                        bool_to_int(data.get("maintenance_mode", False)),
                    ),
                )

            except Exception as exc:
                error = str(exc)
                print(f"{host}: failed to read {stats_path}: {exc}", flush=True)

        conn.execute(
            """
            INSERT INTO host_status (
                host,
                seen_ts,
                stats_present,
                error,
                source_ts
            )
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(host) DO UPDATE SET
                seen_ts = excluded.seen_ts,
                stats_present = excluded.stats_present,
                error = excluded.error,
                source_ts = excluded.source_ts
            """,
            (host, now, stats_present, error, source_ts),
        )

    remove_disappeared_host_rows(conn, now, config)


def scan_status_files(conn, config, now):
    root = input_root(config, "status_files", monitor_root(config))
    globs = input_globs(config, "status_files", ["*.status"])
    dirs = list_host_dirs(root)
    ignore = ignored_hosts(config)

    for host, host_dir in sorted(dirs.items()):
        if host in ignore:
            continue

        seen_paths = []
        for pattern in globs:
            seen_paths.extend(host_dir.glob(pattern))

        for path in sorted(set(seen_paths)):
            if not path.is_file():
                continue

            function = function_from_globs(path, [".status"])

            try:
                content = read_text_file(path)
                state, ok = evaluate_status_content(config, host, function, content)

                conn.execute(
                    """
                    INSERT INTO status_files (
                        host,
                        function,
                        relpath,
                        content,
                        state,
                        ok,
                        seen_ts
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(host, function) DO UPDATE SET
                        relpath = excluded.relpath,
                        content = excluded.content,
                        state = excluded.state,
                        ok = excluded.ok,
                        seen_ts = excluded.seen_ts
                    """,
                    (
                        host,
                        function,
                        str(path.relative_to(root)),
                        content,
                        state,
                        1 if ok else 0,
                        now,
                    ),
                )

            except Exception as exc:
                print(f"{host}: failed to read status file {path}: {exc}", flush=True)

    remove_disappeared_rows(conn, "status_files", now, config)


def scan_heartbeat_files(conn, config, now):
    root = input_root(config, "heartbeat_files", monitor_root(config))
    globs = input_globs(config, "heartbeat_files", ["*.heartbeat", "*.heartBeat"])
    dirs = list_host_dirs(root)
    ignore = ignored_hosts(config)

    for host, host_dir in sorted(dirs.items()):
        if host in ignore:
            continue

        seen_paths = []
        for pattern in globs:
            seen_paths.extend(host_dir.glob(pattern))

        for path in sorted(set(seen_paths)):
            if not path.is_file():
                continue

            function = function_from_globs(path, [".heartbeat"])
            rule = heartbeat_rule(config, host, function)
            max_age = float(rule.get("max_age_seconds", 180))

            try:
                content = read_text_file(path)
                timestamp_ts = parse_timestamp(content)

                if timestamp_ts is None:
                    raise ValueError("invalid timestamp")

                age = max(0, now - timestamp_ts)
                ok = age <= max_age
                error = None

            except Exception as exc:
                content = ""
                timestamp_ts = None
                age = None
                ok = False
                error = str(exc)

            conn.execute(
                """
                INSERT INTO heartbeat_files (
                    host,
                    function,
                    relpath,
                    content,
                    timestamp_ts,
                    age_seconds,
                    max_age_seconds,
                    ok,
                    error,
                    seen_ts
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(host, function) DO UPDATE SET
                    relpath = excluded.relpath,
                    content = excluded.content,
                    timestamp_ts = excluded.timestamp_ts,
                    age_seconds = excluded.age_seconds,
                    max_age_seconds = excluded.max_age_seconds,
                    ok = excluded.ok,
                    error = excluded.error,
                    seen_ts = excluded.seen_ts
                """,
                (
                    host,
                    function,
                    str(path.relative_to(root)),
                    content,
                    timestamp_ts,
                    age,
                    max_age,
                    1 if ok else 0,
                    error,
                    now,
                ),
            )

    remove_disappeared_rows(conn, "heartbeat_files", now, config)


def scan_success_files(conn, config, now):
    root = input_root(config, "success_files", success_root(config))
    globs = input_globs(config, "success_files", ["*.success"])
    dirs = list_host_dirs(root)
    ignore = ignored_hosts(config)

    for host, host_dir in sorted(dirs.items()):
        if host in ignore:
            continue

        seen_paths = []
        for pattern in globs:
            seen_paths.extend(host_dir.glob(pattern))

        for path in sorted(set(seen_paths)):
            if not path.is_file():
                continue

            script = function_from_globs(path, [".success"])
            rule = success_rule(config, host, script)
            max_age = float(rule.get("max_age_seconds", 90000))

            try:
                content = read_text_file(path)
                timestamp_ts = parse_timestamp(content)

                if timestamp_ts is None:
                    raise ValueError("invalid timestamp")

                age = max(0, now - timestamp_ts)
                ok = age <= max_age
                error = None

            except Exception as exc:
                content = ""
                timestamp_ts = None
                age = None
                ok = False
                error = str(exc)

            conn.execute(
                """
                INSERT INTO success_files (
                    host,
                    script,
                    relpath,
                    content,
                    timestamp_ts,
                    age_seconds,
                    max_age_seconds,
                    ok,
                    error,
                    seen_ts
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(host, script) DO UPDATE SET
                    relpath = excluded.relpath,
                    content = excluded.content,
                    timestamp_ts = excluded.timestamp_ts,
                    age_seconds = excluded.age_seconds,
                    max_age_seconds = excluded.max_age_seconds,
                    ok = excluded.ok,
                    error = excluded.error,
                    seen_ts = excluded.seen_ts
                """,
                (
                    host,
                    script,
                    str(path.relative_to(root)),
                    content,
                    timestamp_ts,
                    age,
                    max_age,
                    1 if ok else 0,
                    error,
                    now,
                ),
            )

    remove_disappeared_rows(conn, "success_files", now, config)


def remove_disappeared_rows(conn, table_name, now, config):
    grace = int(ingest_config(config).get("interval_seconds", 2)) * 3
    conn.execute(
        f"DELETE FROM {table_name} WHERE seen_ts < ?",
        (now - grace,),
    )


def remove_disappeared_host_rows(conn, now, config):
    # Keep expected hosts so missing hosts can be displayed explicitly.
    expected = expected_hosts(config)
    grace = int(ingest_config(config).get("interval_seconds", 2)) * 3

    if expected:
        placeholders = ",".join("?" for _ in expected)
        conn.execute(
            f"DELETE FROM host_status WHERE seen_ts < ? AND host NOT IN ({placeholders})",
            [now - grace, *sorted(expected)],
        )
    else:
        conn.execute(
            "DELETE FROM host_status WHERE seen_ts < ?",
            (now - grace,),
        )


def prune_old_data(conn, config, now):
    retention_days = int(ingest_config(config).get("retention_days", config.get("retention_days", 30)))
    cutoff = now - retention_days * 86400

    conn.execute(
        "DELETE FROM system_stats WHERE source_ts < ?",
        (cutoff,),
    )


def ingest_loop():
    while True:
        try:
            config = load_config()
            ingest_once()
            sleep_seconds = int(ingest_config(config).get("interval_seconds", 2))
        except Exception as exc:
            print(f"ingest loop error: {exc}", flush=True)
            sleep_seconds = 2

        time.sleep(max(1, sleep_seconds))


def update_frequency_file(config):
    return Path(path_config(config).get("update_frequency_file", "/run/monitorUpdateFrequency"))


def allowed_update_frequencies(config):
    values = ui_config(config).get("allowed_update_frequencies_seconds", [2, 10, 60])
    return [int(v) for v in values]


def default_update_frequency(config):
    return int(ui_config(config).get("default_update_frequency_seconds", 10))


def read_update_frequency(config):
    path = update_frequency_file(config)
    allowed = set(allowed_update_frequencies(config))
    default = default_update_frequency(config)

    try:
        value = int(path.read_text(encoding="utf-8").strip())
        if value in allowed:
            return value
    except Exception:
        pass

    return default


def write_update_frequency(config, seconds):
    allowed = set(allowed_update_frequencies(config))

    if seconds not in allowed:
        raise ValueError(f"frequency must be one of {sorted(allowed)}")

    path = update_frequency_file(config)
    path.write_text(f"{seconds}\n", encoding="utf-8")


def graph_ranges(config):
    ranges = ui_config(config).get("graph_ranges")

    if isinstance(ranges, dict) and ranges:
        return ranges

    return {
        "10m": {"label": "10 min", "hours": 1 / 6, "max_points_per_metric": 600},
        "3h": {"label": "3 h", "hours": 3, "max_points_per_metric": 720},
        "24h": {"label": "24 h", "hours": 24, "max_points_per_metric": 1440},
        "7d": {"label": "7 d", "hours": 168, "max_points_per_metric": 1008},
    }


def default_graph_range(config):
    default = ui_config(config).get("default_graph_range", "24h")
    ranges = graph_ranges(config)
    return default if default in ranges else next(iter(ranges.keys()))


def get_requested_graph_range(config):
    ranges = graph_ranges(config)
    key = request.args.get("range", default_graph_range(config))

    if key not in ranges:
        key = default_graph_range(config)

    item = ranges[key]
    hours = float(item.get("hours", 24))
    max_points = int(item.get("max_points_per_metric", 1440))
    bucket_seconds = max(1, math.ceil((hours * 3600) / max_points))

    return key, item, hours, bucket_seconds


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.route("/api/ui-settings")
def api_ui_settings():
    config = load_config()
    return jsonify({
        "update_frequency": {
            "seconds": read_update_frequency(config),
            "allowed": allowed_update_frequencies(config),
        },
        "graph_ranges": graph_ranges(config),
        "default_graph_range": default_graph_range(config),
    })


@app.route("/api/update-frequency", methods=["GET", "POST"])
def api_update_frequency():
    config = load_config()

    if request.method == "GET":
        return jsonify({
            "seconds": read_update_frequency(config),
            "allowed": allowed_update_frequencies(config),
        })

    payload = request.get_json(silent=True) or {}

    try:
        seconds = int(payload.get("seconds"))
        write_update_frequency(config, seconds)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({
        "seconds": seconds,
        "allowed": allowed_update_frequencies(config),
    })


@app.route("/api/hosts")
def api_hosts():
    config = load_config()
    ignore = ignored_hosts(config)
    expected = expected_hosts(config)

    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT
                hs.host,
                hs.seen_ts,
                hs.stats_present,
                hs.error,
                ss.source_ts,
                ss.cpu_percent,
                ss.ram_percent,
                ss.cpu_temp_c,
                ss.maintenance_mode
            FROM host_status hs
            LEFT JOIN system_stats ss
              ON ss.host = hs.host
             AND ss.source_ts = (
                SELECT MAX(source_ts)
                FROM system_stats
                WHERE host = hs.host
             )
            ORDER BY hs.host ASC
            """
        ).fetchall()

    now = int(time.time())
    by_host = {}

    for row in rows:
        if row["host"] in ignore:
            continue

        source_ts = row["source_ts"]
        age_seconds = None if source_ts is None else max(0, now - source_ts)

        by_host[row["host"]] = {
            "host": row["host"],
            "expected": row["host"] in expected,
            "stats_present": bool(row["stats_present"]),
            "error": row["error"],
            "source_ts": source_ts,
            "age_seconds": age_seconds,
            "cpu_percent": row["cpu_percent"],
            "ram_percent": row["ram_percent"],
            "cpu_temp_c": row["cpu_temp_c"],
            "maintenance_mode": bool(row["maintenance_mode"]) if row["maintenance_mode"] is not None else False,
        }

    for host in expected:
        if host in ignore:
            continue

        by_host.setdefault(host, {
            "host": host,
            "expected": True,
            "stats_present": False,
            "error": None,
            "source_ts": None,
            "age_seconds": None,
            "cpu_percent": None,
            "ram_percent": None,
            "cpu_temp_c": None,
            "maintenance_mode": False,
        })

    return jsonify({"hosts": [by_host[h] for h in sorted(by_host.keys())]})


@app.route("/api/series")
def api_series():
    config = load_config()
    ignore = ignored_hosts(config)
    range_key, range_item, hours, bucket_seconds = get_requested_graph_range(config)
    cutoff = int(time.time() - hours * 3600)

    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT
                host,
                ((source_ts / ?) * ?) AS bucket_ts,
                AVG(cpu_percent) AS cpu_percent,
                AVG(ram_percent) AS ram_percent,
                AVG(cpu_temp_c) AS cpu_temp_c,
                MAX(maintenance_mode) AS maintenance_mode
            FROM system_stats
            WHERE source_ts >= ?
            GROUP BY host, bucket_ts
            ORDER BY host ASC, bucket_ts ASC
            """,
            (bucket_seconds, bucket_seconds, cutoff),
        ).fetchall()

    by_host = {}

    for row in rows:
        host = row["host"]

        if host in ignore:
            continue

        host_entry = by_host.setdefault(
            host,
            {
                "host": host,
                "metrics": {
                    "cpu_percent": [],
                    "ram_percent": [],
                    "cpu_temp_c": [],
                    "maintenance_mode": [],
                },
            },
        )

        ts_ms = int(row["bucket_ts"]) * 1000

        for metric in host_entry["metrics"].keys():
            value = row[metric]

            if value is not None:
                host_entry["metrics"][metric].append({
                    "ts": ts_ms,
                    "value": value,
                })

    return jsonify({
        "range": range_key,
        "range_label": range_item.get("label", range_key),
        "hours": hours,
        "bucket_seconds": bucket_seconds,
        "hosts": [by_host[host] for host in sorted(by_host.keys())],
    })


@app.route("/api/status-files")
def api_status_files():
    config = load_config()
    ignore = ignored_hosts(config)

    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT
                host,
                function,
                relpath,
                content,
                state,
                ok
            FROM status_files
            ORDER BY ok ASC, host ASC, function ASC
            """
        ).fetchall()

    items = []

    for row in rows:
        if row["host"] in ignore:
            continue

        items.append({
            "host": row["host"],
            "function": row["function"],
            "relpath": row["relpath"],
            "content": row["content"],
            "state": row["state"],
            "ok": bool(row["ok"]),
        })

    return jsonify({"status_files": items})


@app.route("/api/heartbeat-files")
def api_heartbeat_files():
    config = load_config()
    ignore = ignored_hosts(config)

    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT
                host,
                function,
                relpath,
                content,
                timestamp_ts,
                age_seconds,
                max_age_seconds,
                ok,
                error
            FROM heartbeat_files
            ORDER BY ok ASC, host ASC, function ASC
            """
        ).fetchall()

    items = []

    for row in rows:
        if row["host"] in ignore:
            continue

        items.append({
            "host": row["host"],
            "function": row["function"],
            "relpath": row["relpath"],
            "content": row["content"],
            "timestamp_ts": row["timestamp_ts"],
            "age_seconds": row["age_seconds"],
            "max_age_seconds": row["max_age_seconds"],
            "ok": bool(row["ok"]),
            "error": row["error"],
        })

    return jsonify({"heartbeat_files": items})


@app.route("/api/success-files")
def api_success_files():
    config = load_config()
    ignore = ignored_hosts(config)

    with db_connect() as conn:
        rows = conn.execute(
            """
            SELECT
                host,
                script,
                relpath,
                content,
                timestamp_ts,
                age_seconds,
                max_age_seconds,
                ok,
                error
            FROM success_files
            ORDER BY ok ASC, host ASC, script ASC
            """
        ).fetchall()

    items = []

    for row in rows:
        if row["host"] in ignore:
            continue

        items.append({
            "host": row["host"],
            "script": row["script"],
            "relpath": row["relpath"],
            "content": row["content"],
            "timestamp_ts": row["timestamp_ts"],
            "age_seconds": row["age_seconds"],
            "max_age_seconds": row["max_age_seconds"],
            "ok": bool(row["ok"]),
            "error": row["error"],
        })

    return jsonify({"success_files": items})


def start_background_thread():
    thread = threading.Thread(target=ingest_loop, daemon=True)
    thread.start()


init_db()
start_background_thread()
