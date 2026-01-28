FROM syncthing/syncthing:1

ENV STNOUPGRADE=1 \
    STNODEFAULTFOLDER=1 \
    # Web UI не требуется: оставляем только localhost в контейнере
    STGUIADDRESS=127.0.0.1:8384 \
    # Кладём конфиг/БД в persistent storage Amvera (/data)
    HOME=/data/syncthing \
    STHOMEDIR=/data/syncthing/config \
    # Путь до yaml-конфига (копируем в image).
    SYNC_CONFIG=/app/sync-folders.yaml \
    # Профиль игноров для `.stignore_sync` (minimal|dev)
    STIGNORE_PROFILE=dev

RUN apk add --no-cache python3 py3-yaml

WORKDIR /app

COPY sync-folders.yaml /app/sync-folders.yaml
COPY templates/stignore /app/templates/stignore
COPY docker/configure_syncthing.py /app/docker/configure_syncthing.py
COPY docker/start-syncthing.sh /usr/local/bin/start-syncthing.sh
COPY docker/docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh

RUN chmod +x /usr/local/bin/start-syncthing.sh /usr/local/bin/docker-entrypoint.sh

EXPOSE 8384 22000/tcp 22000/udp 21027/udp

# В Amvera обычно монтируется один persistent root (/data), поэтому держим всё там.
VOLUME ["/data"]

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
