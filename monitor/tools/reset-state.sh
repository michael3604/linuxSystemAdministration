#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="monitor-dashboard.service"
STATE_DIR="/var/lib/monitor-dashboard/state"
SERVICE_USER="monitor-dashboard"

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: Please run as root." >&2
  exit 1
fi

systemctl stop "$SERVICE_NAME" || true
rm -rf "$STATE_DIR"
mkdir -p "$STATE_DIR"
chown "$SERVICE_USER:$SERVICE_USER" "$STATE_DIR"
chmod 750 "$STATE_DIR"
systemctl start "$SERVICE_NAME"

echo "Reset dashboard state/database under $STATE_DIR"
