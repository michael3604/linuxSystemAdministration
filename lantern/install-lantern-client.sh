#!/usr/bin/env bash
set -euo pipefail

APP_SRC="$(cd "$(dirname "$0")" && pwd)"
APP_DST="/opt/lantern-client"
CONFIG_DIR="/etc/lantern"

if [ "$(id -u)" -ne 0 ]; then
  echo "install-lantern-client.sh must run as root" >&2
  exit 1
fi

ensure_debian_packages() {
  local missing=()
  local pkg

  for pkg in "$@"; do
    if ! dpkg-query -W -f='${Status}' "$pkg" 2>/dev/null | grep -q '^install ok installed$'; then
      missing+=("$pkg")
    fi
  done

  if [ "${#missing[@]}" -eq 0 ]; then
    echo "Required Debian packages are already installed."
    return 0
  fi

  echo "Installing missing Debian packages only: ${missing[*]}"
  DEBIAN_FRONTEND=noninteractive apt-get install -y --no-upgrade "${missing[@]}"
}

ensure_debian_packages python3 rsync openssh-client

mkdir -p "$CONFIG_DIR" /run/lantern/local /run/lantern/outbox /run/lantern/config "$APP_DST"

rsync -a --delete \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  "$APP_SRC/client/" "$APP_DST/"
install -o root -g root -m 0644 "$APP_SRC/VERSION" "$APP_DST/VERSION"

client_hostname="${LANTERN_CLIENT_HOSTNAME:-$(hostname -s)}"
ssh_shortcut="${LANTERN_CLIENT_SSH_SHORTCUT:-mainSsh-${client_hostname}}"
remote_snapshot_folder="${LANTERN_REMOTE_SNAPSHOT_FOLDER:-/mnt/lantern/snapshots}"

if [ ! -f "$CONFIG_DIR/client.conf" ]; then
  tmp_conf="$(mktemp)"
  CLIENT_HOSTNAME="$client_hostname" \
  CLIENT_SSH_SHORTCUT="$ssh_shortcut" \
  CLIENT_REMOTE_SNAPSHOT_FOLDER="$remote_snapshot_folder" \
  python3 - <<'PY' > "$tmp_conf"
import json
import os

host_name = os.environ["CLIENT_HOSTNAME"]
ssh_shortcut = os.environ["CLIENT_SSH_SHORTCUT"]
remote_snapshot_folder = os.environ["CLIENT_REMOTE_SNAPSHOT_FOLDER"]

config = {
    "version": 5,
    "hostName": host_name,
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
        "sshShortcut": ssh_shortcut,
        "remoteSnapshotFolder": remote_snapshot_folder,
        "keepPerHost": 10,
        "useLinkDest": True,
        "sshTimeoutSeconds": 10,
    },
}
print(json.dumps(config, indent=2))
PY
  install -o root -g root -m 0640 "$tmp_conf" "$CONFIG_DIR/client.conf"
  rm -f "$tmp_conf"
  echo "Created $CONFIG_DIR/client.conf for host '$client_hostname' using SSH shortcut '$ssh_shortcut'. Please review it."
else
  echo "$CONFIG_DIR/client.conf already exists; leaving it unchanged."
fi

if [ ! -f /run/lantern/config/updateFrequency ]; then
  printf '120\n' > /run/lantern/config/updateFrequency
fi

rm -f /usr/local/bin/createDataPoint
install -o root -g root -m 0755 "$APP_SRC/bin/lanternDataPoint" /usr/local/bin/lanternDataPoint
install -o root -g root -m 0755 "$APP_SRC/bin/lantern-client" /usr/local/bin/lantern-client
install -o root -g root -m 0644 "$APP_SRC/systemd/lantern-client.service" /etc/systemd/system/lantern-client.service

systemctl daemon-reload

echo "LANtern client installed to $APP_DST."
echo "Review /etc/lantern/client.conf, then run: systemctl enable --now lantern-client.service"
