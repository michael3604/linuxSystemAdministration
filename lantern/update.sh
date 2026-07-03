#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE_VERSION_FILE="$SCRIPT_DIR/VERSION"

if [ ! -f "$SOURCE_VERSION_FILE" ]; then
  echo "Missing release VERSION file: $SOURCE_VERSION_FILE" >&2
  exit 1
fi

SOURCE_VERSION="$(tr -d '[:space:]' < "$SOURCE_VERSION_FILE")"
FORCE=0
DO_SERVER=0
DO_CLIENT=0
AUTO=1

usage() {
  cat <<USAGE
Usage: $0 [--server] [--client] [--force]

By default, updates installed LANtern components only when the release VERSION
is different from the installed component VERSION.

Options:
  --server   Check/update the server component, even if auto-detection would skip it.
  --client   Check/update the client component, even if auto-detection would skip it.
  --force    Reinstall selected/installed components even when versions match.
  --help     Show this help.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --server)
      DO_SERVER=1
      AUTO=0
      ;;
    --client)
      DO_CLIENT=1
      AUTO=0
      ;;
    --force)
      FORCE=1
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
  shift
done

run_root() {
  if [ "$(id -u)" -eq 0 ]; then
    "$@"
  else
    sudo "$@"
  fi
}

unit_known() {
  local unit="$1"
  systemctl list-unit-files --type=service 2>/dev/null | awk '{print $1}' | grep -qx "$unit"
}

component_detected() {
  local unit="$1"
  local install_dir="$2"
  unit_known "$unit" || [ -d "$install_dir" ]
}

installed_version() {
  local version_file="$1"
  if [ -f "$version_file" ]; then
    tr -d '[:space:]' < "$version_file"
  else
    printf 'missing'
  fi
}

service_restart_if_known() {
  local unit="$1"
  if unit_known "$unit"; then
    run_root systemctl restart "$unit"
  fi
}

maybe_update_component() {
  local name="$1"
  local install_dir="$2"
  local version_file="$3"
  local installer="$4"
  local service="$5"

  local current_version
  current_version="$(installed_version "$version_file")"

  if [ "$FORCE" -eq 0 ] && [ "$current_version" = "$SOURCE_VERSION" ]; then
    echo "$name is already at version $SOURCE_VERSION; skipping."
    return 0
  fi

  if [ "$FORCE" -eq 1 ]; then
    echo "Reinstalling $name version $SOURCE_VERSION (--force)."
  else
    echo "Updating $name from version $current_version to $SOURCE_VERSION."
  fi

  run_root "$installer"
  service_restart_if_known "$service"
}

if [ "$AUTO" -eq 1 ]; then
  if component_detected lantern-server.service /opt/lantern-server; then
    DO_SERVER=1
  fi
  if component_detected lantern-client.service /opt/lantern-client; then
    DO_CLIENT=1
  fi
fi

if [ "$DO_SERVER" -eq 0 ] && [ "$DO_CLIENT" -eq 0 ]; then
  echo "No installed LANtern components detected."
  echo "Use install-lantern-server.sh or install-lantern-client.sh for first install,"
  echo "or run: $0 --server and/or $0 --client"
  exit 0
fi

if [ "$DO_SERVER" -eq 1 ]; then
  maybe_update_component \
    "LANtern server" \
    "/opt/lantern-server" \
    "/opt/lantern-server/VERSION" \
    "$SCRIPT_DIR/install-lantern-server.sh" \
    "lantern-server.service"
fi

if [ "$DO_CLIENT" -eq 1 ]; then
  maybe_update_component \
    "LANtern client" \
    "/opt/lantern-client" \
    "/opt/lantern-client/VERSION" \
    "$SCRIPT_DIR/install-lantern-client.sh" \
    "lantern-client.service"
fi
