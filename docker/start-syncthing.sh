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
root="${FILE_BROWSER_ROOT:-/data/syncthing/versions}"
port="${FILE_BROWSER_PORT:-80}"

if [ "${FILE_BROWSER_ENABLED:-0}" = "1" ]; then
  mkdir -p "$root" >/dev/null 2>&1 || true
  echo "[file-browser] enabled: serving $root on :$port"
  # NB: без аутентификации. Если нужно ограничить доступ — добавим позже.
  python3 -m http.server "$port" --directory "$root" &
else
  # Amvera обычно ожидает, что containerPort будет слушаться.
  # Чтобы деплой не ломался при FILE_BROWSER_ENABLED=0, поднимаем заглушку.
  echo "[file-browser] disabled: serving stub on :$port"
  python3 - <<PY &
from http.server import BaseHTTPRequestHandler, HTTPServer

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(404)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"File browser is disabled (FILE_BROWSER_ENABLED=0).\\n")

    def log_message(self, format, *args):  # noqa: A002
        return

HTTPServer(("0.0.0.0", int("$port")), Handler).serve_forever()
PY
fi

# Настройка папок/игноров/версий на основе sync-folders.yaml и AMVERA_ALLOWED_DEVICE_IDS.
python3 /app/docker/configure_syncthing.py \
  --config "${SYNC_CONFIG:-/app/sync-folders.yaml}" \
  --home "$STHOMEDIR" \
  --node amvera

exec /bin/syncthing serve --home "$STHOMEDIR" --no-browser
