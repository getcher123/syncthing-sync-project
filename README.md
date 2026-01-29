# Syncthing Sync Project (2×WSL + Amvera)

## Описание

Проект разворачивает Syncthing на трёх нодах:
- 2 локальные машины с WSL (`wsl_a`, `wsl_b`) — равноправные, могут и принимать, и отдавать.
- 1 нода в Amvera (`amvera`) — docker + persistent storage, работает через relays (без обязательных входящих TCP портов).

## Цель и какую проблему решает

Синхронизировать **фиксированный набор папок** между несколькими машинами и иметь “облачную” третью ноду:
- чтобы данные сходились, даже если одна из локальных машин временно недоступна;
- чтобы на Amvera сохранялись версии файлов (бэкап на случай удаления/перезаписи);
- чтобы версии можно было скачать вручную через публичный HTTP file browser.

## Стек

- Syncthing (P2P синхронизация, relays)
- WSL (2 локальные ноды)
- Docker (для Amvera; опционально для WSL)
- Amvera (деплой контейнера + persistent storage)
- Python скрипты (генерация/патч `config.xml`, установка `.stignore`)

## Конфигурация

В репозитории хранится только “шаблон” и настройки:
- `sync-folders.yaml` — список folder IDs + настройки (коммитится).

Локальные пути и device IDs — в отдельном файле, который **не коммитится**:
- `sync-folders.local.yaml` — реальные пути папок + device IDs (`wsl_a/wsl_b/amvera`) (игнорируется git).
- Пример: `sync-folders.local.example.yaml`.

## Важные особенности

- Syncthing не делает “тихий last-write-wins”: при параллельных изменениях одного файла на разных нодах возможны `sync-conflict` копии.
- По умолчанию Syncthing пытается direct-соединение и использует relays только если direct недоступен. “Relay-only” режим отдельно настраивается.
- `.stignore` не синхронизируется между устройствами. Поэтому используется схема:
  - локальный `.stignore` содержит `#include .stignore_sync`
  - `.stignore_sync` — обычный файл и синхронизируется (общий список игноров). Профиль: `dev`.

## Запуск на WSL нодах

### 1) Получить Device ID

Выбери режим на каждой WSL машине:
- native: установлен `syncthing` в WSL
- docker: используется образ `syncthing/syncthing:1`

```bash
./scripts/wsl/get_device_id_native.sh
# или
./scripts/wsl/get_device_id_docker.sh
```

### 2) Создать локальный конфиг

Скопируй пример и заполни под свои две машины:

```bash
cp sync-folders.local.example.yaml sync-folders.local.yaml
```

Заполни в `sync-folders.local.yaml`:
- `nodes.wsl_a.device_id`, `nodes.wsl_b.device_id`
- `nodes.amvera.device_id` (после первого деплоя Amvera можно взять Device ID из логов)
- реальные пути папок (секция `folders:`)

### 3) Применить настройки Syncthing + установить игноры

Native-режим:

```bash
# Создаст config.xml, если его ещё нет (и заодно покажет Device ID)
./scripts/wsl/get_device_id_native.sh ~/.local/state/syncthing >/dev/null
python3 scripts/configure_syncthing.py --node wsl_a --home ~/.local/state/syncthing
python3 scripts/install_stignore.py --node wsl_a --profile dev --create-missing-dirs
```

Docker-режим:

```bash
./scripts/wsl/get_device_id_docker.sh ~/.local/state/syncthing-docker >/dev/null
python3 scripts/configure_syncthing.py --node wsl_a --home ~/.local/state/syncthing-docker/config
python3 scripts/install_stignore.py --node wsl_a --profile dev --create-missing-dirs
```

Повтори для `wsl_b` (замени `--node wsl_a` на `--node wsl_b`). После этого перезапусти Syncthing на каждой ноде.

## Деплой на Amvera

### 1) Persistent storage

Нужен persistent storage минимум **10 GB** (можно увеличить позже). Всё состояние контейнера хранится в `/data`.

### 2) Переменные окружения в Amvera

Обязательные:
- `AMVERA_ALLOWED_DEVICE_IDS` — единственный источник правды: список Device ID всех нод, которым разрешено подключаться к Amvera (через запятую/пробел).

Поведение allowlist:
- Amvera удаляет из `config.xml` все устройства, которых нет в списке.
- Amvera шарит папки только с устройствами из списка.

Опциональные:
- `FILE_BROWSER_ENABLED=0` — выключить публичный file browser
- `FILE_BROWSER_PORT=...` — сменить порт (по умолчанию `80`)
- `STIGNORE_PROFILE=dev`

Versioning на Amvera (по умолчанию включён: 3 копии, хранение ~30 дней):
- `ST_VERSIONING_TYPE=simple`
- `ST_VERSIONING_KEEP=3`
- `ST_VERSIONING_CLEANOUT_DAYS=30`

### 3) Что будет доступно снаружи

Публичный HTTP file browser (без аутентификации) для скачивания версий:
- порт: `80`
- корень: `/data/syncthing/versions`

Syncthing Web UI остаётся только внутри контейнера (`127.0.0.1:8384`).

### 4) Как получить Device ID Amvera

При первом старте контейнер печатает `Device ID: ...` в лог (Run logs в Amvera UI).

## Локальный тест (3 ноды + сервер)

Для быстрой проверки синхронизации без контейнеров на нодах:

```bash
./scripts/local_test_up.sh
```

Скрипт поднимает 3 локальные ноды (`n1/n2/n3`) и одну серверную (docker) с `AMVERA_ALLOWED_DEVICE_IDS`,
создаёт по одному файлу на каждой ноде и проверяет, что они синхронизировались на всех участниках.
В конце выводит Device IDs, порты, список файлов и проверки по checksum.

Остановить и удалить всё:

```bash
./scripts/local_test_down.sh
```
