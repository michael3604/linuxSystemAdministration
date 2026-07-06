#!/usr/bin/env bash
set -euo pipefail

APP_SRC="$(cd "$(dirname "$0")" && pwd)"
APP_DST="/opt/lantern-server"
CONFIG_DIR="/etc/lantern"
STATE_DIR="/var/lib/lantern/state"
SUCCESS_DIR="/var/lib/success"
RUN_DIR="/run/lantern"

if [ "$(id -u)" -ne 0 ]; then
  echo "install-lantern-server.sh must run as root" >&2
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

ensure_debian_packages python3 python3-venv rsync sqlite3

if ! id lantern >/dev/null 2>&1; then
  useradd --system --home /var/lib/lantern --shell /usr/sbin/nologin lantern
fi

mkdir -p "$APP_DST" "$CONFIG_DIR" "$STATE_DIR" "$SUCCESS_DIR" "$RUN_DIR/config" "$RUN_DIR/snapshots"
chmod 1777 "$RUN_DIR/snapshots"
rsync -a --delete \
  --exclude 'client/' \
  --exclude '.git/' \
  --exclude '__pycache__/' \
  --exclude '*.pyc' \
  "$APP_SRC/server" "$APP_SRC/requirements.txt" "$APP_SRC/VERSION" "$APP_DST/"

python3 -m venv "$APP_DST/venv"
"$APP_DST/venv/bin/pip" install --upgrade pip >/dev/null
"$APP_DST/venv/bin/pip" install -r "$APP_DST/requirements.txt"

if [ ! -f "$CONFIG_DIR/server.conf" ]; then
  install -o root -g lantern -m 0640 "$APP_SRC/config/server.conf.example" "$CONFIG_DIR/server.conf"
  echo "Created $CONFIG_DIR/server.conf. Please review it."
fi

# Generate and apply a tmpfiles rule from the active server config. This is
# important for ramdisk-backed paths such as /mnt/lantern: after every boot the
# shared snapshot root must be recreated before clients connect, and it must be
# 1777 from the beginning. Clients intentionally do not create/chmod this root.
mkdir -p /etc/tmpfiles.d
SERVER_CONF="$CONFIG_DIR/server.conf" python3 - <<'PY_TMPFILES' > /etc/tmpfiles.d/lantern-server.conf
import json
import os
from pathlib import Path

conf = Path(os.environ['SERVER_CONF'])
with conf.open('r', encoding='utf-8') as fh:
    data = json.load(fh)
paths = data.get('paths', {})

snapshot = Path(paths.get('snapshotFolder', '/run/lantern/snapshots'))
state = Path(paths.get('stateFolder', '/var/lib/lantern/state'))
success = Path(paths.get('successFilesFolder', '/var/lib/success'))
update_file = Path(paths.get('updateFrequencyFile', '/run/lantern/config/updateFrequency'))

lines = []
seen = set()

def add(line: str) -> None:
    if line not in seen:
        seen.add(line)
        lines.append(line)

def add_parent_dirs(path: Path, mode='0755', user='root', group='root') -> None:
    # Add parents below common top-level mount/system directories, so tmpfiles
    # can recreate an empty ramdisk tree such as /mnt/lantern without trying to
    # manage broad directories like /mnt, /var, /run, or /.
    parents = list(path.parents)
    for parent in reversed(parents[:-1]):
        if str(parent) in ('', '/', '/mnt', '/var', '/run', '/etc', '/opt'):
            continue
        add(f'd {parent} {mode} {user} {group} -')

add('d /run/lantern 0755 lantern lantern -')
add('d /run/lantern/config 0755 lantern lantern -')
add('d /run/lantern/snapshots 1777 root root -')
add('f /run/lantern/config/updateFrequency 0644 lantern lantern -')
add('w /run/lantern/config/updateFrequency - - - - 120')

add_parent_dirs(snapshot)
add(f'd {snapshot} 1777 root root -')

add_parent_dirs(update_file.parent)
add(f'd {update_file.parent} 0755 lantern lantern -')
add(f'f {update_file} 0644 lantern lantern -')
add(f'w {update_file} - - - - 120')

add_parent_dirs(state)
add(f'd {state} 0750 lantern lantern -')

add_parent_dirs(success)
add(f'd {success} 0755 root root -')

print('\n'.join(lines))
PY_TMPFILES

systemd-tmpfiles --create /etc/tmpfiles.d/lantern-server.conf

# Also apply permissions immediately, because systemd-tmpfiles will not chmod an
# existing directory if ownership/permissions were changed manually in some cases.
SERVER_CONF="$CONFIG_DIR/server.conf" python3 - <<'PY_PATHS'
import json
import os
from pathlib import Path

conf = Path(os.environ['SERVER_CONF'])
with conf.open('r', encoding='utf-8') as fh:
    data = json.load(fh)
paths = data.get('paths', {})
for key, fallback in (
    ('stateFolder', '/var/lib/lantern/state'),
    ('successFilesFolder', '/var/lib/success'),
):
    Path(paths.get(key, fallback)).mkdir(parents=True, exist_ok=True)
snapshot = Path(paths.get('snapshotFolder', '/run/lantern/snapshots'))
snapshot.mkdir(parents=True, exist_ok=True)
os.chmod(snapshot, 0o1777)
update_file = Path(paths.get('updateFrequencyFile', '/run/lantern/config/updateFrequency'))
update_file.parent.mkdir(parents=True, exist_ok=True)
if not update_file.exists():
    update_file.write_text('120\n', encoding='utf-8')
PY_PATHS

chown -R lantern:lantern "$STATE_DIR" "$RUN_DIR/config"
chmod 0750 "$STATE_DIR"
chmod 0755 "$RUN_DIR" "$SUCCESS_DIR"
chmod 1777 "$RUN_DIR/snapshots"
if [ ! -f "$RUN_DIR/config/updateFrequency" ]; then
  printf '120\n' > "$RUN_DIR/config/updateFrequency"
fi
chown lantern:lantern "$RUN_DIR/config/updateFrequency"
chmod 0644 "$RUN_DIR/config/updateFrequency"

install -o root -g root -m 0644 "$APP_SRC/systemd/lantern-server.service" /etc/systemd/system/lantern-server.service
install -o root -g root -m 0644 "$APP_SRC/systemd/lantern-server-update-frequency-manager.service" /etc/systemd/system/lantern-server-update-frequency-manager.service

# Generate a path hardening override from the active server config. This keeps custom
# ramdisk paths such as /mnt/lantern working.
mkdir -p /etc/systemd/system/lantern-server.service.d
SERVER_CONF="$CONFIG_DIR/server.conf" python3 - <<'PY2' > /etc/systemd/system/lantern-server.service.d/paths.conf
import json
import os
from pathlib import Path

conf = Path(os.environ['SERVER_CONF'])
with conf.open('r', encoding='utf-8') as fh:
    data = json.load(fh)
paths = data.get('paths', {})

def parent(path_value, fallback):
    if not path_value:
        return fallback
    p = Path(path_value)
    return str(p.parent if p.suffix or p.name else p)

snapshot_root = parent(paths.get('snapshotFolder'), '/run/lantern')
update_root = parent(paths.get('updateFrequencyFile'), '/run/lantern/config')
state_root = paths.get('stateFolder', '/var/lib/lantern/state')
success_root = paths.get('successFilesFolder', '/var/lib/success')

print('[Service]')
print('ReadOnlyPaths=')
print('ReadWritePaths=')
print(f'ReadOnlyPaths=/opt/lantern-server /etc/lantern/server.conf {success_root}')

def add_path(paths_list, candidate):
    candidate_path = Path(candidate)
    for existing in paths_list:
        try:
            candidate_path.relative_to(Path(existing))
            return
        except ValueError:
            pass
    paths_list[:] = [existing for existing in paths_list if not Path(existing).is_relative_to(candidate_path)]
    paths_list.append(str(candidate_path))

write_paths = []
for item in (state_root, snapshot_root, update_root):
    add_path(write_paths, item)
print('ReadWritePaths=' + ' '.join(write_paths))
PY2

install -o root -g root -m 0755 "$APP_SRC/tools/lantern-check" /usr/local/bin/lantern-check
install -o root -g root -m 0755 "$APP_SRC/tools/lantern-db-status" /usr/local/bin/lantern-db-status
install -o root -g root -m 0755 "$APP_SRC/tools/lantern-reset-state" /usr/local/bin/lantern-reset-state
install -o root -g root -m 0644 "$APP_SRC/tools/check_inputs.py" "$APP_DST/check_inputs.py"
install -o root -g root -m 0644 "$APP_SRC/tools/db_status.py" "$APP_DST/db_status.py"

systemctl daemon-reload
systemctl enable --now lantern-server.service

echo "LANtern server installed to $APP_DST."
echo "Review /etc/lantern/server.conf."
echo "Server service: lantern-server.service"
echo "Update-frequency manager service: lantern-server-update-frequency-manager.service"
echo "Update-frequency manager is installed but not enabled automatically."
