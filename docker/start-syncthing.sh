#!/bin/sh

set -eu

STHOMEDIR="${STHOMEDIR:-/var/syncthing/config}"

mkdir -p "$STHOMEDIR" /data/sync >/dev/null 2>&1 || true

# Первичная генерация ключей/конфига — печатает Device ID в stdout (чтобы увидеть в логах Amvera).
if [ ! -f "$STHOMEDIR/config.xml" ]; then
  echo "[bootstrap] syncthing generate --home=$STHOMEDIR"
  /bin/syncthing generate --home "$STHOMEDIR" --no-default-folder --skip-port-probing
fi

# Простой HTTP file browser (для ручного скачивания версий из /data/syncthing/versions).
if [ "${FILE_BROWSER_ENABLED:-0}" = "1" ]; then
  root="${FILE_BROWSER_ROOT:-/data/syncthing/versions}"
  port="${FILE_BROWSER_PORT:-80}"
  mkdir -p "$root" >/dev/null 2>&1 || true
  echo "[file-browser] serving $root on :$port"
  # NB: без аутентификации. Если нужно ограничить доступ — добавим позже.
  python3 -m http.server "$port" --directory "$root" &
fi

# Настройка папок/игноров/версий на основе sync-folders.yaml и AMVERA_ALLOWED_DEVICE_IDS.
python3 /app/docker/configure_syncthing.py \
  --config "${SYNC_CONFIG:-/app/sync-folders.yaml}" \
  --home "$STHOMEDIR" \
  --node amvera

exec /bin/syncthing serve --home "$STHOMEDIR" --no-browser
