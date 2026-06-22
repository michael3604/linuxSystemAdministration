#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/scripts/monitor"
SERVICE_NAME="monitor-dashboard.service"
CONFIG_FILE="/var/lib/monitor-dashboard/config/monitor.conf"

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: Please run as root." >&2
  exit 1
fi

cd "$APP_ROOT"

if [[ -d .git ]]; then
  git pull --ff-only
fi

if ! python3 -m json.tool "$CONFIG_FILE" >/dev/null; then
  echo "ERROR: Invalid JSON config: $CONFIG_FILE" >&2
  exit 1
fi

"$APP_ROOT/venv/bin/pip" install -r "$APP_ROOT/requirements.txt"

systemctl daemon-reload
systemctl restart "$SERVICE_NAME"
systemctl --no-pager --full status "$SERVICE_NAME"
