#!/usr/bin/env bash
set -euo pipefail

ST_HOME="${1:-$HOME/.local/state/syncthing}"

if ! command -v syncthing >/dev/null 2>&1; then
  echo "ERROR: syncthing не установлен." >&2
  echo "Для Ubuntu/Debian: sudo apt-get update && sudo apt-get install -y syncthing" >&2
  exit 2
fi

mkdir -p "$ST_HOME"

if [[ ! -f "$ST_HOME/config.xml" ]]; then
  syncthing generate --home "$ST_HOME" --no-default-folder --skip-port-probing >/dev/null
fi

device_id="$(sed -n 's/.*<device id=\"\\([A-Z0-9-]\\+\\)\".*/\\1/p' \"$ST_HOME/config.xml\" | head -n 1)"

if [[ -z "${device_id:-}" ]]; then
  echo "ERROR: не удалось извлечь Device ID из $ST_HOME/config.xml" >&2
  exit 2
fi

echo "$device_id"
