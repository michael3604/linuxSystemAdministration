# LANtern

LANtern is a small self-hosted LAN status dashboard for homelab systems.

It deliberately stays file-based at the edge:

- the LANtern client writes one regular `status.json` file
- independent scripts create sparse service datapoints by calling `lanternDataPoint`
- an external success-file system may rsync timestamp-only `.success` files to the server
- the LANtern server ingests completed client snapshots and external success files into SQLite
- alerting is intentionally out of scope

## v0.5.15 behaviour notes

- Runtime no longer depends on `/scripts` at all.
- Server runtime is installed to `/opt/lantern-server`.
- Client runtime is installed to `/opt/lantern-client`.
- `lanternDataPoint` is installed to `/usr/local/bin/lanternDataPoint` and writes via `/opt/lantern-client`.
- Systemd service names are `lantern-server.service` and `lantern-client.service`.
- Primary installer names are `install-lantern-server.sh` and `install-lantern-client.sh`.
- No compatibility installer names are shipped; obsolete names are intentionally removed.
- Installers can be run from any working directory and do not modify the source/download directory.
- Server and client installers do not run `apt-get update`; they only install missing Debian packages with `apt-get install --no-upgrade`.

## Server paths

Default server config:

```text
/etc/lantern/server.conf
```

Default server data:

```text
/opt/lantern-server                  installed server app
/var/lib/lantern/state/lantern.sqlite3
/run/lantern/config/updateFrequency
/mnt/lantern/snapshots/<host>/<snapshotId>/
/var/lib/success/<host>/<service>.success
```

## Client paths

Default client config:

```text
/etc/lantern/client.conf
```

Default client runtime:

```text
/opt/lantern-client                  installed client app
/usr/local/bin/lanternDataPoint       datapoint helper
/usr/local/bin/lantern-client        manual client helper
/run/lantern/local/status.json
/run/lantern/local/<service>.json
/run/lantern/outbox/<snapshotId>/
```

Success files are not created, moved, or synced by LANtern. They are an external input on the server.


## Update installed components

`update.sh` compares the release `VERSION` file against the installed component version files:

```text
/opt/lantern-server/VERSION
/opt/lantern-client/VERSION
```

By default it updates only installed components whose version differs from the release version:

```bash
sudo /tmp/lantern/update.sh
```

Force reinstall of the same version:

```bash
sudo /tmp/lantern/update.sh --force
```

Explicitly update only one component:

```bash
sudo /tmp/lantern/update.sh --server
sudo /tmp/lantern/update.sh --client
```

## Install server

The installer can be run from anywhere. Example with an unpacked archive in `/tmp`:

```bash
tar -xzf lantern-v0.5.15.tar.gz -C /tmp
sudo /tmp/lantern/install-lantern-server.sh
sudo nano /etc/lantern/server.conf
sudo systemctl restart lantern-server.service
```

Open:

```text
http://<server-ip>:8010/
```

## Install client

```bash
tar -xzf lantern-v0.5.15.tar.gz -C /tmp
sudo /tmp/lantern/install-lantern-client.sh
sudo nano /etc/lantern/client.conf
sudo systemctl enable --now lantern-client.service
```

On first install, `/etc/lantern/client.conf` is generated from `hostname -s`:

```json
"hostName": "<hostname>",
"sshShortcut": "mainSsh-<hostname>"
```

## Create service datapoints

Simple status datapoint:

```bash
lanternDataPoint "printerReachable" "good" "printer reachable"
```

Numeric datapoint:

```bash
lanternDataPoint "freeSpaceChecker" "good" 48 "%" "/ has 48% free space"
```

Bad datapoint:

```bash
lanternDataPoint "backupDisk" "bad" "backup disk is missing"
```

The command writes atomically to:

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

The client creates snapshot directories ending in `.inWork`, transfers into them, then atomically renames them to the final snapshot name.

```text
/mnt/lantern/snapshots/main/20260626T123010UTC.inWork/
/mnt/lantern/snapshots/main/20260626T123010UTC/
```

The server ignores `*.inWork` directories.

If enabled, the client uses `rsync --link-dest` over SSH. In `mode: local`, it hardlinks only from the previous completed destination snapshot and copies changed files safely, so it also works when `/run` and `/mnt` are different filesystems.

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

Server:

```bash
systemctl status lantern-server.service
journalctl -u lantern-server.service -n 100 --no-pager
lantern-check
lantern-db-status
sudo lantern-reset-state
```

Client:

```bash
systemctl status lantern-client.service
journalctl -u lantern-client.service -n 100 --no-pager
lantern-client once
```

## Dashboard notes

- Host metrics graph uses dual vertical axes: `%` on the left for CPU/RAM/maintenance and `°C` on the right for CPU temperature.
- Automatic dashboard refreshes preserve vertical page scroll position and horizontal table-scroll positions.
- Service graphs receive an explicit graph-start carry-forward point from the API, using `serviceCurrent` as fallback.
- Host-loss shading uses configured `hostStatusMaxAgeSeconds`.
- Tables are horizontally scrollable on small screens; key name/show columns remain sticky.


## Ignoring old service rows

Services can be hidden from the current table and service-history graph without deleting SQLite history. Add patterns to `/etc/lantern/server.conf`:

```json
"services": {
  "ignored": {
    "*": ["debug*"],
    "main": ["testStatus"]
  }
}
```

For timestamp-only success files, use the same shape under `successFiles.ignored`. Patterns without `/` match service names; patterns with `/` match `host/service`.

## Snapshot directory permissions

The server snapshot root is a shared client inbox. LANtern creates it with mode `1777` rather than plain `0777`:

```text
/mnt/lantern/snapshots
/run/lantern/snapshots
```

The sticky bit allows different SSH client users to create their own host directories while preventing them from deleting or renaming directories owned by other users. Host subdirectories such as `paper/` or `main/` are still created by the respective client.

For ramdisk-backed paths, `install-lantern-server.sh` also writes `/etc/tmpfiles.d/lantern-server.conf`. This recreates the configured snapshot root and update-frequency file at boot. Clients deliberately do **not** create or chmod the shared snapshot root; they only create their own host subdirectory below it.
