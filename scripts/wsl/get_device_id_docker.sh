#!/usr/bin/env bash
set -euo pipefail

ST_DIR="${1:-$HOME/.local/state/syncthing-docker}"

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker не найден." >&2
  exit 2
fi

mkdir -p "$ST_DIR/config"

if [[ ! -f "$ST_DIR/config/config.xml" ]]; then
  docker run --rm \
    -v "$ST_DIR":/var/syncthing \
    syncthing/syncthing:1 \
    generate --home /var/syncthing/config --no-default-folder --skip-port-probing >/dev/null
fi

device_id="$(sed -n 's/.*<device id=\"\\([A-Z0-9-]\\+\\)\".*/\\1/p' \"$ST_DIR/config/config.xml\" | head -n 1)"

if [[ -z "${device_id:-}" ]]; then
  echo "ERROR: не удалось извлечь Device ID из $ST_DIR/config/config.xml" >&2
  exit 2
fi

echo "$device_id"
