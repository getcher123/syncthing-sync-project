#!/bin/sh

set -eu

[ -n "${UMASK:-}" ] && umask "$UMASK"

if [ "$(id -u)" = '0' ]; then
  if [ -z "${PCAP:-}" ]; then
    setcap -r /bin/syncthing 2>/dev/null || true
  else
    setcap "$PCAP" /bin/syncthing
  fi

  chown "${PUID:-1000}:${PGID:-1000}" "${HOME:-/data/syncthing}" 2>/dev/null || true

  exec su-exec "${PUID:-1000}:${PGID:-1000}" \
    env HOME="${HOME:-/data/syncthing}" \
    /usr/local/bin/start-syncthing.sh
fi

exec /usr/local/bin/start-syncthing.sh
