#!/usr/bin/env bash
set -euo pipefail

APP_SRC="$(cd "$(dirname "$0")" && pwd)"
CONFIG_DIR="/etc/lantern"

if [ "$(id -u)" -ne 0 ]; then
  echo "install-client.sh must run as root" >&2
  exit 1
fi

apt-get update
apt-get install -y python3 rsync openssh-client

mkdir -p "$CONFIG_DIR" /run/lantern/local /run/lantern/outbox /run/lantern/config

if [ ! -f "$CONFIG_DIR/client.conf" ]; then
  install -o root -g root -m 0640 "$APP_SRC/config/client.conf.example" "$CONFIG_DIR/client.conf"
  echo "Created $CONFIG_DIR/client.conf. Please review it."
fi

if [ ! -f /run/lantern/config/updateFrequency ]; then
  printf '120\n' > /run/lantern/config/updateFrequency
fi

if [ "$(readlink -f "$APP_SRC/createDataPoint")" != "$(readlink -f /scripts/lantern/createDataPoint 2>/dev/null || true)" ]; then
  install -o root -g root -m 0755 "$APP_SRC/createDataPoint" /scripts/lantern/createDataPoint
fi
install -o root -g root -m 0644 "$APP_SRC/systemd/lantern-client.service" /etc/systemd/system/lantern-client.service

systemctl daemon-reload

echo "LANtern client installed."
echo "Review /etc/lantern/client.conf, then run: systemctl enable --now lantern-client.service"
