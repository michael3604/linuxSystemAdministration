#!/usr/bin/env bash
set -euo pipefail

APP_ROOT="/scripts/monitor"
SERVICE_USER="monitor-dashboard"
SERVICE_NAME="monitor-dashboard.service"
RUNTIME_DIR="/var/lib/monitor-dashboard"
CONFIG_DIR="$RUNTIME_DIR/config"
STATE_DIR="$RUNTIME_DIR/state"
CONFIG_FILE="$CONFIG_DIR/monitor.conf"
EXAMPLE_CONFIG="$APP_ROOT/config/monitor.conf.example"
TMPFILES_CONF="/etc/tmpfiles.d/monitor-dashboard.conf"

if [[ $EUID -ne 0 ]]; then
  echo "ERROR: Please run as root." >&2
  exit 1
fi

if [[ ! -d "$APP_ROOT" ]]; then
  echo "ERROR: $APP_ROOT does not exist." >&2
  echo "Install the repository into /scripts/monitor first." >&2
  exit 1
fi

if [[ ! -f "$EXAMPLE_CONFIG" ]]; then
  echo "ERROR: Missing example config: $EXAMPLE_CONFIG" >&2
  exit 1
fi

if ! id "$SERVICE_USER" >/dev/null 2>&1; then
  adduser --system --group --home /nonexistent --no-create-home "$SERVICE_USER"
fi

apt update
apt install -y python3 python3-venv sqlite3 curl

mkdir -p "$CONFIG_DIR" "$STATE_DIR"

chown -R root:root "$APP_ROOT"
chown root:"$SERVICE_USER" "$RUNTIME_DIR" "$CONFIG_DIR"
chown "$SERVICE_USER":"$SERVICE_USER" "$STATE_DIR"

chmod 755 /scripts
chmod 755 "$APP_ROOT"
chmod 755 "$APP_ROOT/app" "$APP_ROOT/app/templates" "$APP_ROOT/config" "$APP_ROOT/systemd" "$APP_ROOT/tools" 2>/dev/null || true
chmod 750 "$RUNTIME_DIR" "$CONFIG_DIR" "$STATE_DIR"

if [[ ! -f "$CONFIG_FILE" ]]; then
  install -o root -g "$SERVICE_USER" -m 0640 "$EXAMPLE_CONFIG" "$CONFIG_FILE"

  cat <<MSG

Created default config:

  $CONFIG_FILE

It was copied from:

  $EXAMPLE_CONFIG

Please review host lists, ignored hosts, input folders, status rules,
heartbeat rules, success-file rules, bind address and port.

MSG
else
  echo "Keeping existing config: $CONFIG_FILE"
fi

if ! python3 -m json.tool "$CONFIG_FILE" >/dev/null; then
  echo "ERROR: Invalid JSON config: $CONFIG_FILE" >&2
  exit 1
fi

python3 -m venv "$APP_ROOT/venv"
"$APP_ROOT/venv/bin/pip" install --upgrade pip
"$APP_ROOT/venv/bin/pip" install -r "$APP_ROOT/requirements.txt"

cat > "$TMPFILES_CONF" <<TMPFILES
# monitor-dashboard runtime files
d /var/lib/monitor-dashboard 0750 root $SERVICE_USER -
d /var/lib/monitor-dashboard/config 0750 root $SERVICE_USER -
d /var/lib/monitor-dashboard/state 0750 $SERVICE_USER $SERVICE_USER -
f /run/monitorUpdateFrequency 0644 $SERVICE_USER $SERVICE_USER - -
w /run/monitorUpdateFrequency - - - - 10
TMPFILES

systemd-tmpfiles --create "$TMPFILES_CONF"

# Make sure the runtime file exists even on systems where tmpfiles behaves differently.
if [[ ! -f /run/monitorUpdateFrequency ]]; then
  printf '10\n' > /run/monitorUpdateFrequency
fi
chown "$SERVICE_USER:$SERVICE_USER" /run/monitorUpdateFrequency
chmod 0644 /run/monitorUpdateFrequency

systemctl link "$APP_ROOT/systemd/$SERVICE_NAME" >/dev/null 2>&1 || true
systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

cat <<MSG

Installed/restarted $SERVICE_NAME

Local config:
  $CONFIG_FILE

Local state:
  $STATE_DIR

Dashboard:
  http://<server-ip>:8010

MSG
