#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import yaml
except Exception as exc:  # pragma: no cover
    print(
        "ERROR: PyYAML не найден. Установи: python3 -m pip install pyyaml",
        file=sys.stderr,
    )
    raise


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = PROJECT_ROOT / "templates" / "stignore"


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("Некорректный YAML: ожидается объект верхнего уровня")
    return data


def merge_local_config(base: dict, local: dict) -> dict:
    merged = dict(base)
    merged_nodes = dict((base.get("nodes") or {}))
    local_nodes = local.get("nodes") or {}
    if isinstance(local_nodes, dict):
        for node_name, node_cfg in local_nodes.items():
            if isinstance(node_cfg, dict):
                merged_nodes[node_name] = {**(merged_nodes.get(node_name) or {}), **node_cfg}
    merged["nodes"] = merged_nodes

    local_folders = local.get("folders") or {}
    if isinstance(local_folders, dict):
        folders = merged.get("folders") or []
        if isinstance(folders, list):
            for item in folders:
                if not isinstance(item, dict):
                    continue
                folder_id = item.get("id")
                if not folder_id:
                    continue
                overrides = local_folders.get(str(folder_id))
                if not isinstance(overrides, dict):
                    continue
                paths = item.get("paths")
                if not isinstance(paths, dict):
                    paths = {}
                    item["paths"] = paths
                for k, v in overrides.items():
                    if k in ("wsl_a", "wsl_b", "amvera") and isinstance(v, str) and v:
                        paths[k] = v
    return merged


def iter_folder_paths(config: dict, node: str):
    folders = config.get("folders")
    if not isinstance(folders, list):
        raise ValueError("В конфиге нет массива folders")
    for item in folders:
        if not isinstance(item, dict):
            continue
        folder_id = item.get("id")
        label = item.get("label", folder_id)
        paths = item.get("paths", {})
        if not isinstance(paths, dict):
            continue
        folder_path = paths.get(node)
        if not folder_path:
            continue
        yield str(folder_id), str(label), str(folder_path)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_text(path: Path, content: str, *, force: bool) -> bool:
    if path.exists() and not force:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Создаёт .stignore (локальный) и .stignore_sync (синхронизируемый) в корнях папок из sync-folders.yaml.",
    )
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "sync-folders.yaml"),
        help="Путь до sync-folders.yaml",
    )
    parser.add_argument(
        "--node",
        required=True,
        choices=["wsl_a", "wsl_b", "amvera"],
        help="Имя ноды из sync-folders.yaml",
    )
    parser.add_argument(
        "--profile",
        default="dev",
        choices=["minimal", "dev"],
        help="Шаблон игноров для .stignore_sync",
    )
    parser.add_argument(
        "--create-missing-dirs",
        action="store_true",
        help="Создавать корневые директории, если их нет",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Перезаписать .stignore и .stignore_sync (осторожно)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Ничего не писать, только показать план действий",
    )
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    config = load_yaml(config_path)
    local_path = config_path.with_name("sync-folders.local.yaml")
    if local_path.exists():
        config = merge_local_config(config, load_yaml(local_path))

    stignore_template = (TEMPLATES_DIR / ".stignore").read_text(encoding="utf-8")
    stignore_sync_template = (
        TEMPLATES_DIR
        / (".stignore_sync.dev" if args.profile == "dev" else ".stignore_sync.minimal")
    ).read_text(encoding="utf-8")

    changes = 0
    for folder_id, label, raw_path in iter_folder_paths(config, args.node):
        expanded = Path(os.path.expanduser(raw_path)).resolve()
        stignore_path = expanded / ".stignore"
        stignore_sync_path = expanded / ".stignore_sync"

        if not expanded.exists():
            if args.create_missing_dirs:
                if args.dry_run:
                    print(f"[mkdir] {expanded}  ({folder_id}: {label})")
                else:
                    ensure_dir(expanded)
                    changes += 1
            else:
                print(
                    f"[skip] {expanded} не существует (folder={folder_id}); добавь --create-missing-dirs если нужно",
                    file=sys.stderr,
                )
                continue

        if args.dry_run:
            action = "overwrite" if args.force else "create-if-missing"
            print(f"[{action}] {stignore_path}")
            print(f"[{action}] {stignore_sync_path} (profile={args.profile})")
            continue

        if write_text(stignore_path, stignore_template, force=args.force):
            changes += 1
        if write_text(stignore_sync_path, stignore_sync_template, force=args.force):
            changes += 1

    if args.dry_run:
        return 0

    print(f"OK: изменений {changes}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
