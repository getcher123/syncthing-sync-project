#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

try:
    import yaml
except Exception:  # pragma: no cover
    print("ERROR: PyYAML не найден. Установи: python3 -m pip install pyyaml", file=sys.stderr)
    raise


PROJECT_ROOT = Path(__file__).resolve().parents[1]


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


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def expand_path(raw: str) -> str:
    return str(Path(os.path.expanduser(raw)).resolve())


def find_or_add_device(root: ET.Element, template: ET.Element, *, device_id: str, name: str, addresses: list[str]) -> None:
    for dev in root.findall("device"):
        if dev.get("id") == device_id:
            return

    new_dev = copy.deepcopy(template)
    new_dev.set("id", device_id)
    new_dev.set("name", name)

    for addr in list(new_dev.findall("address")):
        new_dev.remove(addr)
    for addr in addresses:
        addr_el = ET.Element("address")
        addr_el.text = addr
        new_dev.append(addr_el)

    root.append(new_dev)


def find_or_add_folder(
    root: ET.Element,
    template: ET.Element,
    *,
    folder_id: str,
    label: str,
    path: str,
    folder_type: str,
    ignore_perms: bool,
    device_ids: list[str],
) -> None:
    existing = None
    for f in root.findall("folder"):
        if f.get("id") == folder_id:
            existing = f
            break

    folder = existing or copy.deepcopy(template)
    folder.set("id", folder_id)
    folder.set("label", label)
    folder.set("path", path)
    folder.set("type", folder_type)
    folder.set("ignorePerms", "true" if ignore_perms else "false")

    for dev in list(folder.findall("device")):
        folder.remove(dev)
    for did in device_ids:
        dev_el = ET.Element("device")
        dev_el.set("id", did)
        dev_el.set("introducedBy", "")
        enc_el = ET.Element("encryptionPassword")
        enc_el.text = ""
        dev_el.append(enc_el)
        folder.append(dev_el)

    # На WSL нодах versioning выключаем явно.
    ver = folder.find("versioning")
    if ver is not None:
        ver.attrib.pop("type", None)

    if existing is None:
        root.append(folder)


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch syncthing config.xml for WSL nodes from sync-folders.yaml.")
    parser.add_argument(
        "--config",
        default=str(PROJECT_ROOT / "sync-folders.yaml"),
        help="Путь до sync-folders.yaml",
    )
    parser.add_argument("--node", required=True, choices=["wsl_a", "wsl_b"], help="Имя ноды")
    parser.add_argument(
        "--home",
        default=str(Path("~/.local/state/syncthing").expanduser()),
        help="Syncthing home directory (содержит config.xml, cert.pem, key.pem)",
    )
    args = parser.parse_args()

    config_path = Path(args.config).resolve()
    cfg = load_yaml(config_path)
    local_path = config_path.with_name("sync-folders.local.yaml")
    if local_path.exists():
        cfg = merge_local_config(cfg, load_yaml(local_path))
    nodes = cfg.get("nodes") or {}
    if not isinstance(nodes, dict):
        raise ValueError("nodes должен быть объектом")

    # Device IDs must be filled in YAML.
    wsl_a_id = str((nodes.get("wsl_a") or {}).get("device_id") or "").strip()
    wsl_b_id = str((nodes.get("wsl_b") or {}).get("device_id") or "").strip()
    amvera_id = str((nodes.get("amvera") or {}).get("device_id") or "").strip()
    amvera_domain = str((nodes.get("amvera") or {}).get("domain") or "").strip()

    def is_missing(value: str) -> bool:
        return not value or value.strip().upper() == "REQUIRED"

    home_dir = Path(args.home).expanduser().resolve()
    config_xml = home_dir / "config.xml"
    if not config_xml.exists():
        print(
            f"ERROR: нет {config_xml}.\n"
            "Сначала создай его командой:\n"
            f"- native: ./scripts/wsl/get_device_id_native.sh '{home_dir}'\n"
            "- docker: ./scripts/wsl/get_device_id_docker.sh '~/.local/state/syncthing-docker'\n",
            file=sys.stderr,
        )
        return 2

    tree = ET.parse(config_xml)
    root = tree.getroot()

    local_device = root.find("device")
    local_id = local_device.get("id") if local_device is not None else ""
    if not local_id:
        print("ERROR: не удалось определить local device id из config.xml", file=sys.stderr)
        return 2

    defaults_device = root.find("defaults/device")
    defaults_folder = root.find("defaults/folder")
    if defaults_device is None or defaults_folder is None:
        print("ERROR: defaults templates not found in config.xml", file=sys.stderr)
        return 2

    other_wsl_id = wsl_b_id if args.node == "wsl_a" else wsl_a_id
    other_wsl_name = "wsl_b" if args.node == "wsl_a" else "wsl_a"

    # Remote device entries
    remote_device_ids: list[str] = []

    if not is_missing(other_wsl_id):
        remote_device_ids.append(other_wsl_id)
        find_or_add_device(root, defaults_device, device_id=other_wsl_id, name=other_wsl_name, addresses=["dynamic"])
    else:
        print(f"WARN: {other_wsl_name}.device_id не задан — нода будет работать без второй WSL ноды.", file=sys.stderr)

    if not is_missing(amvera_id):
        remote_device_ids.append(amvera_id)
        amvera_addresses = ["dynamic"]
        if amvera_domain and amvera_domain.upper() != "REQUIRED":
            # Опционально: если Amvera доступна по прямому TCP (порт Syncthing 22000).
            amvera_addresses = [f"tcp://{amvera_domain}:22000", "dynamic"]
        find_or_add_device(root, defaults_device, device_id=amvera_id, name="amvera", addresses=amvera_addresses)
    else:
        print("WARN: amvera.device_id не задан — нода будет работать без Amvera.", file=sys.stderr)

    # GUI локально
    gui = root.find("gui")
    if gui is not None:
        addr = gui.find("address")
        if addr is not None:
            addr.text = "127.0.0.1:8384"
    options = root.find("options")
    if options is not None:
        start_browser = options.find("startBrowser")
        if start_browser is not None:
            start_browser.text = "false"

    folders = cfg.get("folders") or []
    if not isinstance(folders, list):
        raise ValueError("folders должен быть массивом")

    for item in folders:
        if not isinstance(item, dict):
            continue
        folder_id = str(item.get("id") or "").strip()
        if not folder_id:
            continue
        label = str(item.get("label") or folder_id)
        folder_type = str(item.get("type") or "sendreceive")
        ignore_perms = bool(item.get("ignore_perms", True))
        paths = item.get("paths") or {}
        if not isinstance(paths, dict):
            continue
        raw_path = paths.get(args.node)
        if not raw_path or raw_path == "REQUIRED_LOCAL":
            continue
        folder_path = expand_path(raw_path)
        ensure_dir(Path(folder_path))

        find_or_add_folder(
            root,
            defaults_folder,
            folder_id=folder_id,
            label=label,
            path=folder_path,
            folder_type=folder_type,
            ignore_perms=ignore_perms,
            device_ids=[local_id, *remote_device_ids],
        )

    ET.indent(tree, space="    ")
    tree.write(config_xml, encoding="utf-8")
    print(f"OK: обновлён {config_xml}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
