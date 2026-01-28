#!/bin/sh

set -eu

STHOMEDIR="${STHOMEDIR:-/var/syncthing/config}"

mkdir -p "$STHOMEDIR" /data/sync >/dev/null 2>&1 || true

# Первичная генерация ключей/конфига — печатает Device ID в stdout (чтобы увидеть в логах Amvera).
if [ ! -f "$STHOMEDIR/config.xml" ]; then
  echo "[bootstrap] syncthing generate --home=$STHOMEDIR"
  /bin/syncthing generate --home "$STHOMEDIR" --no-default-folder --skip-port-probing
fi

# Настройка папок/игноров/версий на основе sync-folders.yaml (и env с device ids).
python3 /app/docker/configure_syncthing.py \
  --config "${SYNC_CONFIG:-/app/sync-folders.yaml}" \
  --home "$STHOMEDIR" \
  --node amvera

exec /bin/syncthing serve --home "$STHOMEDIR" --no-browser
