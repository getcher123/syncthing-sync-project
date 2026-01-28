# Syncthing: 3 ноды (2×WSL + Amvera)

Цель: синхронизация фиксированного набора папок между тремя нодами:
- `wsl_a` (WSL, native или docker)
- `wsl_b` (WSL, native или docker)
- `amvera` (только docker + постоянное хранилище)

## Файлы проекта

- `sync-folders.yaml` — единый список папок для синхронизации и пути на каждой ноде.
- `docker/Dockerfile` — образ Syncthing для Amvera (ориентирован на persistent storage в `/data`).

## Важные ограничения (чтобы ожидания совпали с реальностью)

- Syncthing не делает “автоматический last-write-wins без конфликтов”.
  Если один и тот же файл изменён на разных нодах офлайн, при встрече будут `sync-conflict` копии.
- Чтобы минимизировать риск потери данных, обычно включают versioning (например, только на Amvera как “бэкап-ноде”).

## Что уже задано

В `sync-folders.yaml` уже внесены папки:
- `C:\\BI core XP`
- `C:\\syncthing-sync-project`
- `C:\\ud-mvp2`
- `C:\\screen.vision`
- `C:\\Life`
- `C:\\informika`
- `C:\\AIHUB-reps`

А также отдельная папка “диалогов Codex” (путь нужно уточнить и вписать).

## Что нужно уточнить (чтобы собрать рабочую схему)

1) “Папка диалогов Codex” — какой именно путь синхронизируем?
   - Например: `/home/<user>/.codex/sessions` и/или `/home/<user>/.codex/archived_sessions`
   - Важно: `auth.json` и токены синхронизировать не стоит.

2) Есть ли у обеих WSL машин доступ в интернет?
   - Если да — можно полагаться на relay/global discovery.
   - Если нет — Amvera им недоступна, нужен VPN/иной канал.

3) Amvera и TCP входящие порты:
   - по докам Amvera внешний TCP доступ даётся через контроллеры и ограничен портами: `5432` (POSTGRES), `27017` (MONGO), `6379` (REDIS).
   - для Syncthing можно использовать TCP контроллер `MONGO` (порт `27017`) и пробросить его на `containerPort: 22000` (см. `amvera.yaml`).
   - даже без входящего TCP Syncthing сможет работать через relays (все ноды с интернетом).

4) Нужно ли реально синхронизировать “тяжёлые” каталоги целиком?
   - `node_modules`, `.next`, `dist`, `build`, `.venv`, `__pycache__` обычно лучше исключить через `.stignore`.
   - Подтверди, что именно исключаем (или ничего не исключаем).

5) Политика конфликтов:
   - ок ли `sync-conflict` файлы (и разруливать вручную),
   - или нужен строго “одна нода главная” для части папок (Send Only / Receive Only)?

## Рекомендуемые настройки (опционально, но сильно помогает)

- На всех папках: `Ignore Permissions = on` (WSL ↔ Linux контейнер).
- Versioning включить на Amvera (например “Staggered”), на WSL можно выключить.
- Не синхронизировать конфиг Syncthing (`/data/syncthing` или `~/.local/state/syncthing`) между нодами, иначе можно получить одинаковые Device ID.

## `.stignore` / общие игноры

Syncthing **не синхронизирует** файл `.stignore` между устройствами. Поэтому используем схему:
- в каждой папке создаём локальный `.stignore` с одной строкой `#include .stignore_sync`
- файл `.stignore_sync` обычный (синхронизируется) и содержит общий список игноров

Шаблоны лежат в `templates/stignore/`, а установка делается скриптом:

```bash
python3 scripts/install_stignore.py --node wsl_a --profile dev --create-missing-dirs
python3 scripts/install_stignore.py --node wsl_b --profile dev --create-missing-dirs
```

Для Amvera (внутри контейнера) путь будет `/data/sync/...` — удобнее создавать эти файлы на WSL нодах:
`.stignore_sync` синхронизируется и приедет на Amvera автоматически, а `.stignore` (локальный) контейнер создаст сам при старте.
