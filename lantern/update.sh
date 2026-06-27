#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
sudo ./install.sh
if systemctl list-unit-files | grep -q '^lantern-client.service'; then
  sudo systemctl restart lantern-client.service || true
fi
