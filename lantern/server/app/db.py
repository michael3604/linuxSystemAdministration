from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS hostStatusHistory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hostName TEXT NOT NULL,
            sourceTimestamp INTEGER NOT NULL,
            rawTimestamp TEXT NOT NULL,
            cpuPercent REAL,
            ramPercent REAL,
            ramAvailableMb REAL,
            cpuTempC REAL,
            maintenanceMode INTEGER NOT NULL DEFAULT 0,
            ingestedAt INTEGER NOT NULL,
            snapshotId TEXT NOT NULL,
            UNIQUE(hostName, sourceTimestamp, snapshotId)
        );

        CREATE TABLE IF NOT EXISTS serviceHistory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hostName TEXT NOT NULL,
            serviceName TEXT NOT NULL,
            sourceType TEXT NOT NULL,
            sourceTimestamp INTEGER NOT NULL,
            rawTimestamp TEXT NOT NULL,
            status TEXT NOT NULL,
            stateNumeric INTEGER NOT NULL,
            value REAL,
            unit TEXT,
            ingestedAt INTEGER NOT NULL,
            snapshotId TEXT,
            UNIQUE(hostName, serviceName, sourceType, sourceTimestamp)
        );

        CREATE TABLE IF NOT EXISTS serviceCurrent (
            hostName TEXT NOT NULL,
            serviceName TEXT NOT NULL,
            sourceType TEXT NOT NULL,
            sourceTimestamp INTEGER NOT NULL,
            rawTimestamp TEXT NOT NULL,
            status TEXT NOT NULL,
            stateNumeric INTEGER NOT NULL,
            value REAL,
            unit TEXT,
            text TEXT,
            lastSeenSnapshotId TEXT,
            updatedAt INTEGER NOT NULL,
            PRIMARY KEY(hostName, serviceName, sourceType)
        );

        CREATE TABLE IF NOT EXISTS hostSnapshotState (
            hostName TEXT PRIMARY KEY,
            lastIngestedSnapshotId TEXT,
            lastIngestedAt INTEGER
        );

        CREATE INDEX IF NOT EXISTS idx_host_history_host_ts ON hostStatusHistory(hostName, sourceTimestamp);
        CREATE INDEX IF NOT EXISTS idx_service_history_service_ts ON serviceHistory(hostName, serviceName, sourceTimestamp);
        CREATE INDEX IF NOT EXISTS idx_service_history_type ON serviceHistory(sourceType);
        """
    )
    conn.commit()


def get_last_snapshot(conn: sqlite3.Connection, host: str) -> str | None:
    row = conn.execute("SELECT lastIngestedSnapshotId FROM hostSnapshotState WHERE hostName=?", (host,)).fetchone()
    return None if row is None else row["lastIngestedSnapshotId"]


def set_last_snapshot(conn: sqlite3.Connection, host: str, snapshot_id: str, ingested_at: int) -> None:
    conn.execute(
        """
        INSERT INTO hostSnapshotState(hostName, lastIngestedSnapshotId, lastIngestedAt)
        VALUES(?, ?, ?)
        ON CONFLICT(hostName) DO UPDATE SET
            lastIngestedSnapshotId=excluded.lastIngestedSnapshotId,
            lastIngestedAt=excluded.lastIngestedAt
        """,
        (host, snapshot_id, ingested_at),
    )


def insert_host_status(conn: sqlite3.Connection, row: Dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO hostStatusHistory(
            hostName, sourceTimestamp, rawTimestamp, cpuPercent, ramPercent,
            ramAvailableMb, cpuTempC, maintenanceMode, ingestedAt, snapshotId
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["hostName"], row["sourceTimestamp"], row["rawTimestamp"], row.get("cpuPercent"),
            row.get("ramPercent"), row.get("ramAvailableMb"), row.get("cpuTempC"),
            1 if row.get("maintenanceMode") else 0, row["ingestedAt"], row["snapshotId"],
        ),
    )


def upsert_service(conn: sqlite3.Connection, row: Dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT OR IGNORE INTO serviceHistory(
            hostName, serviceName, sourceType, sourceTimestamp, rawTimestamp,
            status, stateNumeric, value, unit, ingestedAt, snapshotId
        ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            row["hostName"], row["serviceName"], row["sourceType"], row["sourceTimestamp"],
            row["rawTimestamp"], row["status"], row["stateNumeric"], row.get("value"),
            row.get("unit"), row["ingestedAt"], row.get("snapshotId"),
        ),
    )
    current = conn.execute(
        """
        SELECT sourceTimestamp FROM serviceCurrent
        WHERE hostName=? AND serviceName=? AND sourceType=?
        """,
        (row["hostName"], row["serviceName"], row["sourceType"]),
    ).fetchone()
    if current is None or row["sourceTimestamp"] >= current["sourceTimestamp"]:
        conn.execute(
            """
            INSERT INTO serviceCurrent(
                hostName, serviceName, sourceType, sourceTimestamp, rawTimestamp,
                status, stateNumeric, value, unit, text, lastSeenSnapshotId, updatedAt
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(hostName, serviceName, sourceType) DO UPDATE SET
                sourceTimestamp=excluded.sourceTimestamp,
                rawTimestamp=excluded.rawTimestamp,
                status=excluded.status,
                stateNumeric=excluded.stateNumeric,
                value=excluded.value,
                unit=excluded.unit,
                text=excluded.text,
                lastSeenSnapshotId=excluded.lastSeenSnapshotId,
                updatedAt=excluded.updatedAt
            """,
            (
                row["hostName"], row["serviceName"], row["sourceType"], row["sourceTimestamp"],
                row["rawTimestamp"], row["status"], row["stateNumeric"], row.get("value"),
                row.get("unit"), row.get("text"), row.get("snapshotId"), row["ingestedAt"],
            ),
        )


def latest_hosts(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return conn.execute(
        """
        SELECT h.* FROM hostStatusHistory h
        JOIN (
            SELECT hostName, MAX(sourceTimestamp) AS maxTs FROM hostStatusHistory GROUP BY hostName
        ) latest ON latest.hostName=h.hostName AND latest.maxTs=h.sourceTimestamp
        ORDER BY h.hostName
        """
    ).fetchall()


def host_series(conn: sqlite3.Connection, since_ts: int, bucket_seconds: int) -> List[sqlite3.Row]:
    return conn.execute(
        """
        SELECT hostName,
               (sourceTimestamp / ?) * ? AS bucketTs,
               AVG(cpuPercent) AS cpuPercent,
               AVG(ramPercent) AS ramPercent,
               AVG(ramAvailableMb) AS ramAvailableMb,
               AVG(cpuTempC) AS cpuTempC,
               MAX(maintenanceMode) AS maintenanceMode
        FROM hostStatusHistory
        WHERE sourceTimestamp >= ?
        GROUP BY hostName, bucketTs
        ORDER BY hostName, bucketTs
        """,
        (bucket_seconds, bucket_seconds, since_ts),
    ).fetchall()


def current_services(conn: sqlite3.Connection) -> List[sqlite3.Row]:
    return conn.execute("SELECT * FROM serviceCurrent ORDER BY hostName, serviceName, sourceType").fetchall()


def _parse_service_keys(keys: list[str] | None) -> list[tuple[str, str, str | None]]:
    parsed: list[tuple[str, str, str | None]] = []
    for key in keys or []:
        parts = key.split("/", 2)
        if len(parts) == 3:
            parsed.append((parts[0], parts[1], parts[2]))
        elif len(parts) == 2:
            parsed.append((parts[0], parts[1], None))
    return parsed


def service_series(conn: sqlite3.Connection, since_ts: int, keys: list[str] | None = None) -> List[sqlite3.Row]:
    """Return service points for a graph range plus one carry-forward point.

    Sparse service datapoints may be older than the selected graph range but still
    represent the current state. For every selected service, include the newest
    row before ``since_ts`` as a seed point, then all rows inside the range.
    """
    key_triples = _parse_service_keys(keys)
    rows: list[sqlite3.Row] = []

    if key_triples:
        for host, service, source_type in key_triples:
            type_filter = " AND sourceType=?" if source_type else ""
            type_params: list[Any] = [source_type] if source_type else []
            before = conn.execute(
                f"""
                SELECT hostName, serviceName, sourceType, sourceTimestamp, status,
                       stateNumeric, value, unit
                FROM serviceHistory
                WHERE hostName=? AND serviceName=?{type_filter} AND sourceTimestamp < ?
                ORDER BY sourceTimestamp DESC
                LIMIT 1
                """,
                [host, service, *type_params, since_ts],
            ).fetchone()
            if before is not None:
                rows.append(before)
            rows.extend(conn.execute(
                f"""
                SELECT hostName, serviceName, sourceType, sourceTimestamp, status,
                       stateNumeric, value, unit
                FROM serviceHistory
                WHERE hostName=? AND serviceName=?{type_filter} AND sourceTimestamp >= ?
                ORDER BY sourceTimestamp
                """,
                [host, service, *type_params, since_ts],
            ).fetchall())
        rows.sort(key=lambda r: (r["hostName"], r["serviceName"], r["sourceType"], r["sourceTimestamp"]))
        return rows

    # No explicit selection: include all current services, each seeded with its
    # latest pre-range row and then its in-range rows.
    current = conn.execute("SELECT hostName, serviceName, sourceType FROM serviceCurrent").fetchall()
    return service_series(conn, since_ts, [f"{r['hostName']}/{r['serviceName']}/{r['sourceType']}" for r in current])


def db_stats(conn: sqlite3.Connection) -> Dict[str, Any]:
    result = {}
    for table in ("hostStatusHistory", "serviceHistory", "serviceCurrent", "hostSnapshotState"):
        result[table] = conn.execute(f"SELECT COUNT(*) AS c FROM {table}").fetchone()["c"]
    return result
