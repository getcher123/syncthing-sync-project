#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import os
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml


def load_yaml(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("Некорректный YAML: ожидается объект верхнего уровня")
    return data


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text_if_missing(path: Path, content: str, *, force: bool) -> bool:
    if path.exists() and not force:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def find_or_add_device(root: ET.Element, template: ET.Element, *, device_id: str, name: str, addresses: list[str]) -> None:
    for dev in root.findall("device"):
        if dev.get("id") == device_id:
            return

    new_dev = copy.deepcopy(template)
    new_dev.set("id", device_id)
    new_dev.set("name", name)

    # Replace <address> entries
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
    versioning_type: str,
    versioning_path: str,
    versioning_keep: int,
    versioning_cleanout_days: int,
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

    # Devices in folder
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

    # Versioning (Amvera as backup node)
    ver = folder.find("versioning")
    if ver is None:
        ver = ET.SubElement(folder, "versioning")
    if versioning_type:
        ver.set("type", versioning_type)
    else:
        ver.attrib.pop("type", None)

    # Ensure elements exist
    cleanup = ver.find("cleanupIntervalS")
    if cleanup is None:
        cleanup = ET.SubElement(ver, "cleanupIntervalS")
        cleanup.text = "3600"

    fs_path = ver.find("fsPath")
    if fs_path is None:
        fs_path = ET.SubElement(ver, "fsPath")
    fs_path.text = versioning_path or ""

    fs_type = ver.find("fsType")
    if fs_type is None:
        fs_type = ET.SubElement(ver, "fsType")
        fs_type.text = "basic"

    # Params
    for p in list(ver.findall("param")):
        ver.remove(p)
    if versioning_type == "simple":
        cleanout = ET.SubElement(ver, "param")
        cleanout.set("key", "cleanoutDays")
        cleanout.set("val", str(versioning_cleanout_days))
        keep = ET.SubElement(ver, "param")
        keep.set("key", "keep")
        keep.set("val", str(versioning_keep))

    if existing is None:
        root.append(folder)


def main() -> int:
    parser = argparse.ArgumentParser(description="Configure Syncthing (Amvera node) from sync-folders.yaml and env vars.")
    parser.add_argument("--config", required=True, help="Path to sync-folders.yaml inside container")
    parser.add_argument("--home", required=True, help="Syncthing home directory (STHOMEDIR)")
    parser.add_argument("--node", required=True, choices=["amvera"], help="Only amvera supported in container")
    args = parser.parse_args()

    config_path = Path(args.config)
    home_dir = Path(args.home)
    config_xml = home_dir / "config.xml"

    cfg = load_yaml(config_path)

    # Install ignore files into each configured folder root
    templates_dir = Path("/app/templates/stignore")
    stignore_template = read_text(templates_dir / ".stignore")
    profile = os.environ.get("STIGNORE_PROFILE", "dev").strip() or "dev"
    sync_template_name = ".stignore_sync.dev" if profile == "dev" else ".stignore_sync.minimal"
    stignore_sync_template = read_text(templates_dir / sync_template_name)
    force_ignores = os.environ.get("FORCE_STIGNORE", "").strip() == "1"
    force_ignores_sync = os.environ.get("FORCE_STIGNORE_SYNC", "").strip() == "1"

    folders = cfg.get("folders") or []
    for item in folders:
        if not isinstance(item, dict):
            continue
        paths = item.get("paths") or {}
        if not isinstance(paths, dict):
            continue
        folder_path = paths.get("amvera")
        if not folder_path:
            continue
        root_path = Path(folder_path)
        ensure_dir(root_path)
        write_text_if_missing(root_path / ".stignore", stignore_template, force=force_ignores)
        write_text_if_missing(
            root_path / ".stignore_sync",
            stignore_sync_template,
            force=force_ignores_sync,
        )

    if not config_xml.exists():
        print(f"[configure] skip: нет {config_xml}", file=sys.stderr)
        return 0

    tree = ET.parse(config_xml)
    root = tree.getroot()

    # Make GUI local-only + disable browser
    gui = root.find("gui")
    if gui is not None:
        addr = gui.find("address")
        if addr is not None:
            addr.text = os.environ.get("STGUIADDRESS", "127.0.0.1:8384")
    options = root.find("options")
    if options is not None:
        start_browser = options.find("startBrowser")
        if start_browser is not None:
            start_browser.text = "false"

    # Device IDs from env
    wsl_a_id = os.environ.get("WSL_A_DEVICE_ID", "").strip()
    wsl_b_id = os.environ.get("WSL_B_DEVICE_ID", "").strip()
    if not wsl_a_id or not wsl_b_id:
        print(
            "[configure] WSL_A_DEVICE_ID / WSL_B_DEVICE_ID не заданы — папки/шары в конфиг не добавляю (только .stignore).",
            file=sys.stderr,
        )
        tree.write(config_xml, encoding="utf-8")
        return 0

    # Local device id (from generated config.xml)
    local_device = root.find("device")
    local_id = local_device.get("id") if local_device is not None else ""
    if not local_id:
        print("[configure] Не удалось определить local device id", file=sys.stderr)
        return 1

    defaults_device = root.find("defaults/device")
    defaults_folder = root.find("defaults/folder")
    if defaults_device is None or defaults_folder is None:
        print("[configure] defaults templates not found in config.xml", file=sys.stderr)
        return 1

    find_or_add_device(root, defaults_device, device_id=wsl_a_id, name="wsl_a", addresses=["dynamic"])
    find_or_add_device(root, defaults_device, device_id=wsl_b_id, name="wsl_b", addresses=["dynamic"])

    versioning_type = os.environ.get("ST_VERSIONING_TYPE", "simple").strip()
    versioning_keep = int(os.environ.get("ST_VERSIONING_KEEP", "10").strip() or "10")
    versioning_cleanout_days = int(os.environ.get("ST_VERSIONING_CLEANOUT_DAYS", "30").strip() or "30")

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
        folder_path = paths.get("amvera")
        if not folder_path:
            continue

        ensure_dir(Path(folder_path))

        versions_dir = Path("/data/syncthing/versions") / folder_id
        ensure_dir(versions_dir)

        find_or_add_folder(
            root,
            defaults_folder,
            folder_id=folder_id,
            label=label,
            path=folder_path,
            folder_type=folder_type,
            ignore_perms=ignore_perms,
            device_ids=[local_id, wsl_a_id, wsl_b_id],
            versioning_type=versioning_type,
            versioning_path=str(versions_dir),
            versioning_keep=versioning_keep,
            versioning_cleanout_days=versioning_cleanout_days,
        )

    ET.indent(tree, space="    ")
    tree.write(config_xml, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
