#!/usr/bin/env bash
set -euo pipefail

APP_SRC="$(cd "$(dirname "$0")" && pwd)"
APP_DST="/opt/lantern"
CONFIG_DIR="/etc/lantern"
STATE_DIR="/var/lib/lantern/state"
SUCCESS_DIR="/var/lib/success"
RUN_DIR="/run/lantern"

if [ "$(id -u)" -ne 0 ]; then
  echo "install.sh must run as root" >&2
  exit 1
fi

apt-get update
apt-get install -y python3 python3-venv rsync sqlite3

if ! id lantern >/dev/null 2>&1; then
  useradd --system --home /var/lib/lantern --shell /usr/sbin/nologin lantern
fi

mkdir -p "$APP_DST" "$CONFIG_DIR" "$STATE_DIR" "$SUCCESS_DIR" "$RUN_DIR/config" "$RUN_DIR/snapshots"
rsync -a --delete \
  --exclude 'client/' \
  --exclude '.git/' \
  "$APP_SRC/server" "$APP_SRC/requirements.txt" "$APP_DST/"

python3 -m venv "$APP_DST/venv"
"$APP_DST/venv/bin/pip" install --upgrade pip >/dev/null
"$APP_DST/venv/bin/pip" install -r "$APP_DST/requirements.txt"

if [ ! -f "$CONFIG_DIR/server.conf" ]; then
  install -o root -g lantern -m 0640 "$APP_SRC/config/server.conf.example" "$CONFIG_DIR/server.conf"
  echo "Created $CONFIG_DIR/server.conf. Please review it."
fi

chown -R lantern:lantern "$STATE_DIR" "$RUN_DIR/config"
chmod 0750 "$STATE_DIR"
chmod 0755 "$RUN_DIR" "$RUN_DIR/snapshots" "$SUCCESS_DIR"
if [ ! -f "$RUN_DIR/config/updateFrequency" ]; then
  printf '120\n' > "$RUN_DIR/config/updateFrequency"
fi
chown lantern:lantern "$RUN_DIR/config/updateFrequency"
chmod 0644 "$RUN_DIR/config/updateFrequency"

install -o root -g root -m 0644 "$APP_SRC/systemd/lantern.service" /etc/systemd/system/lantern.service
install -o root -g root -m 0644 "$APP_SRC/systemd/lantern-update-frequency-manager.service" /etc/systemd/system/lantern-update-frequency-manager.service

install -o root -g root -m 0755 "$APP_SRC/tools/lantern-check" /usr/local/bin/lantern-check
install -o root -g root -m 0755 "$APP_SRC/tools/lantern-db-status" /usr/local/bin/lantern-db-status
install -o root -g root -m 0755 "$APP_SRC/tools/lantern-reset-state" /usr/local/bin/lantern-reset-state
install -o root -g root -m 0644 "$APP_SRC/tools/check_inputs.py" "$APP_DST/check_inputs.py"
install -o root -g root -m 0644 "$APP_SRC/tools/db_status.py" "$APP_DST/db_status.py"

systemctl daemon-reload
systemctl enable --now lantern.service

echo "LANtern server installed."
echo "Review /etc/lantern/server.conf."
echo "Update-frequency manager is installed but not enabled automatically."
