#!/usr/bin/env bash
set -euo pipefail

SERVICE_USER="monitor-dashboard"
CONFIG_FILE="/var/lib/monitor-dashboard/config/monitor.conf"
STATE_DIR="/var/lib/monitor-dashboard/state"

echo "== service =="
systemctl is-active monitor-dashboard.service || true

echo

echo "== config =="
python3 -m json.tool "$CONFIG_FILE" >/dev/null && echo "config JSON OK: $CONFIG_FILE"

echo

echo "== paths from config =="
monitor_root="$(python3 -c 'import json; c=json.load(open("/var/lib/monitor-dashboard/config/monitor.conf")); print(c.get("paths",{}).get("monitor_root","/mnt/monitor"))')"
success_root="$(python3 -c 'import json; c=json.load(open("/var/lib/monitor-dashboard/config/monitor.conf")); print(c.get("paths",{}).get("success_root","/mnt/successfiles"))')"

echo "monitor_root=$monitor_root"
echo "success_root=$success_root"

echo

echo "== readability =="
sudo -u "$SERVICE_USER" test -r "$CONFIG_FILE" && echo "config readable"
sudo -u "$SERVICE_USER" find "$monitor_root" -maxdepth 3 -type f | head || true
sudo -u "$SERVICE_USER" find "$success_root" -maxdepth 3 -type f | head || true

echo

echo "== writability =="
sudo -u "$SERVICE_USER" test -w "$STATE_DIR" && echo "state dir writable"
sudo -u "$SERVICE_USER" test -w /run/monitorUpdateFrequency && echo "/run/monitorUpdateFrequency writable"

echo

echo "== API =="
curl -fsS http://127.0.0.1:8010/healthz && echo
curl -fsS http://127.0.0.1:8010/api/hosts | head -c 500 && echo
