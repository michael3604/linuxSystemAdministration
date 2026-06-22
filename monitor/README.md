# Lightweight Monitor Dashboard

Small self-hosted Flask + SQLite dashboard for file-based Linux server monitoring.

It reads read-only input files such as:

```text
/mnt/monitor/<hostname>/systemStats.json
/mnt/monitor/<hostname>/*.status
/mnt/monitor/<hostname>/*.heartbeat
/mnt/successfiles/<hostname>/*.success
```

and stores history locally under:

```text
/var/lib/monitor-dashboard/state/monitor.sqlite3
```

The dashboard itself is served by Waitress on port `8010` by default.

## Install

Expected install path:

```text
/scripts/monitor
```

Example:

```bash
mkdir -p /scripts
cd /scripts
# clone or extract this repository as /scripts/monitor
cd /scripts/monitor
./install.sh
```

The installer creates a local config if missing:

```text
/var/lib/monitor-dashboard/config/monitor.conf
```

from:

```text
/scripts/monitor/config/monitor.conf.example
```

The real config is not part of the public repository.

## Main local paths

```text
/scripts/monitor                         source code / public repo
/var/lib/monitor-dashboard/config         local private config
/var/lib/monitor-dashboard/state          SQLite database and state
/run/monitorUpdateFrequency               runtime update-frequency control file
```

## Dashboard controls

The dashboard has two control groups:

```text
Update frequency: 2 s, 10 s, 60 s
Graph range:      10 min, 3 h, 24 h, 7 d
```

The update frequency is written to:

```text
/run/monitorUpdateFrequency
```

The graph range is a browser display preference and is not written to `/run`.

## Reset

Soft reset: remove history/database but keep config.

```bash
/scripts/monitor/tools/reset-state.sh
```

Hard reset: remove all local runtime data and reinstall.

```bash
systemctl stop monitor-dashboard.service
rm -rf /var/lib/monitor-dashboard
/scripts/monitor/install.sh
```

## UFW

The installer does not open the firewall. Allow LAN access explicitly, for example:

```bash
ufw allow from 192.168.178.0/24 to any port 8010 proto tcp comment 'Monitor dashboard LAN only'
```

## Input file formats

### systemStats.json

```json
{
  "hostname": "main",
  "timestamp": "2026-06-22T13:35:34+00:00",
  "cpu_percent": 1.3,
  "ram_percent": 30.3,
  "cpu_temp_c": 51.9,
  "maintenance_mode": false
}
```

### .status files

Example path:

```text
/mnt/monitor/main/backupDisk.status
```

Example content:

```text
mounted
```

Good/bad content is configured in `status_rules`.

### .heartbeat files

Example path:

```text
/mnt/monitor/main/nmrCloud.heartbeat
```

Example content:

```text
2026-06-22T13:35:34+00:00
```

Max age is configured in `heartbeat_rules`.

### .success files

Example path:

```text
/mnt/successfiles/main/borg-nextcloud.success
```

Example content:

```text
2026-06-22T03:00:00+00:00
```

Max age is configured in `success_file_rules`.
