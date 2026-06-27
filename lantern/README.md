# LANtern


## v0.5.2 behaviour notes

- The default SSH shortcut pattern is `mainSsh-<clientUser>`, for example `mainSsh-paper`.
- Service graphs now receive an explicit graph-start carry-forward point from the API, using `serviceCurrent` as fallback. Slow checks remain visible even when their JSON timestamp is older than the selected range.
- Host-loss shading uses the configured `hostStatusMaxAgeSeconds`, not graph bucket size. This avoids false red bars in short graph ranges when clients update every 120 seconds.
- Tables are horizontally scrollable on small screens; the service Show and Host / Service columns remain sticky, and the host name column remains sticky.

LANtern is a small self-hosted LAN status dashboard for homelab systems.

It deliberately stays file-based at the edge:

- the LANtern client writes one regular `status.json` file
- independent scripts create sparse service datapoints by calling `createDataPoint`
- an external success-file system may rsync timestamp-only `.success` files to the server
- the LANtern server ingests completed client snapshots and external success files into SQLite
- alerting is intentionally out of scope

## Server paths

Default server config:

```text
/etc/lantern/server.conf
```

Default server data:

```text
/opt/lantern                         installed server app
/var/lib/lantern/state/lantern.sqlite3
/run/lantern/config/updateFrequency
/run/lantern/snapshots/<host>/<snapshotId>/
/var/lib/success/<host>/<service>.success
```

## Client paths

Default client config:

```text
/etc/lantern/client.conf
```

Default local client data:

```text
/run/lantern/local/status.json
/run/lantern/local/<service>.json
/run/lantern/outbox/<snapshotId>/
```

Success files are not created, moved, or synced by LANtern. They are an external input on the server.

## Install server

```bash
cd /tmp
sudo mkdir -p /scripts
sudo tar -xzf lantern-v0.5.2.tar.gz -C /scripts
cd /scripts/lantern
sudo ./install.sh
sudo nano /etc/lantern/server.conf
sudo systemctl restart lantern.service
```

Open:

```text
http://<server-ip>:8010/
```

## Install client

```bash
cd /scripts/lantern
sudo ./install-client.sh
sudo nano /etc/lantern/client.conf
sudo systemctl enable --now lantern-client.service
```

The client may run directly from `/scripts/lantern/client`, so it can follow your existing Git/symlink update workflow.

## Create service datapoints

Simple status datapoint:

```bash
/scripts/lantern/createDataPoint "printerReachable" "good" "printer reachable"
```

Numeric datapoint:

```bash
/scripts/lantern/createDataPoint "freeSpaceChecker" "good" 48 "%" "/ has 48% free space"
```

Bad datapoint:

```bash
/scripts/lantern/createDataPoint "backupDisk" "bad" "backup disk is missing"
```

The command writes:

```text
/run/lantern/local/<service>.json
```

Example:

```json
{
  "timestamp": "2026-06-26T12:30:10UTC",
  "status": "good",
  "value": 48,
  "unit": "%",
  "text": "/ has 48% free space"
}
```

## Snapshot transfer

The client creates snapshot directories ending in `.inWork`, rsyncs into them, then atomically renames them to the final snapshot name.

```text
/run/lantern/snapshots/main/20260626T123010UTC.inWork/
/run/lantern/snapshots/main/20260626T123010UTC/
```

The server ignores `*.inWork` directories.

If enabled, the client uses `rsync --link-dest` against the newest completed remote snapshot so unchanged service JSON files do not need to be retransferred.

## Success files

Success files are external. LANtern only reads them.

Default server-side layout:

```text
/var/lib/success/main/googleEmailBackupValidator.success
/var/lib/success/paper/cupsArchive.success
```

Each file must contain exactly one timestamp line, for example:

```text
2026-06-26T12:30:10UTC
```

## Useful commands

```bash
systemctl status lantern.service
journalctl -u lantern.service -n 100 --no-pager
lantern-check
lantern-db-status
sudo lantern-reset-state
```

Client:

```bash
systemctl status lantern-client.service
journalctl -u lantern-client.service -n 100 --no-pager
/scripts/lantern/client/lantern_client.py once
```
