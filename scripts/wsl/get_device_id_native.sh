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
  # В разных версиях Syncthing генерация делается по-разному:
  # - новые: `syncthing generate --home ...`
  # - старые (debian-ds1): `syncthing serve --generate=...`
  if syncthing generate --help >/dev/null 2>&1; then
    syncthing generate --home "$ST_HOME" --no-default-folder >/dev/null
  else
    syncthing serve --generate="$ST_HOME" --no-default-folder >/dev/null
  fi
fi

if syncthing serve --help 2>/dev/null | grep -q -- '--device-id'; then
  device_id="$(syncthing serve --home "$ST_HOME" --device-id 2>/dev/null | tail -n 1)"
else
  device_id="$(sed -n 's/.*<device id=\"\\([A-Z0-9-]\\+\\)\".*/\\1/p' \"$ST_HOME/config.xml\" | head -n 1)"
fi

if [[ -z "${device_id:-}" ]]; then
  echo "ERROR: не удалось извлечь Device ID из $ST_HOME/config.xml" >&2
  exit 2
fi

echo "$device_id"
