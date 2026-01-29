#!/usr/bin/env bash
set -euo pipefail

BASE="/tmp/syncthing-local-test"
IMAGE="syncthing-sync-project:local"
SERVER_NAME="amvera_srv_test"
SERVER_PORT="22010"
SERVER_ADDR="tcp://127.0.0.1:${SERVER_PORT}"
SERVER_BROWSER_PORT="18080"

echo "== Local test start =="
echo "Base: $BASE"
echo "Image: $IMAGE"
echo "Server: $SERVER_NAME"
echo

if ! command -v syncthing >/dev/null 2>&1; then
  echo "ERROR: syncthing не установлен." >&2
  exit 2
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: docker не установлен." >&2
  exit 2
fi

echo "== Build image =="
docker build -t "$IMAGE" -f docker/Dockerfile .
echo

echo "== Cleanup old test (if any) =="
"$(dirname "$0")/local_test_down.sh" >/dev/null 2>&1 || true
echo

mkdir -p "$BASE"

echo "== Create 3 native nodes (n1/n2/n3) =="
for n in n1 n2 n3; do
  mkdir -p "$BASE/$n/home" "$BASE/$n/sync/test-sync"
  device_id="$("$(dirname "$0")/wsl/get_device_id_native.sh" "$BASE/$n/home")"
  echo "$device_id" > "$BASE/$n/device-id.txt"
  echo "$n Device ID: $device_id"
done
echo

echo "== Patch node configs (ports + discovery off) =="
python3 - <<'PY'
import xml.etree.ElementTree as ET
from pathlib import Path

base = Path("/tmp/syncthing-local-test")
nodes = {
    "n1": {"gui": 18384, "listen": 23001},
    "n2": {"gui": 18385, "listen": 23002},
    "n3": {"gui": 18386, "listen": 23003},
}

for name, cfg in nodes.items():
    config_xml = base / name / "home" / "config.xml"
    tree = ET.parse(config_xml)
    root = tree.getroot()

    gui = root.find("gui")
    if gui is not None:
        addr = gui.find("address")
        if addr is not None:
            addr.text = f"127.0.0.1:{cfg['gui']}"

    options = root.find("options")
    if options is None:
        raise SystemExit(f"missing <options> in {config_xml}")

    start_browser = options.find("startBrowser")
    if start_browser is not None:
        start_browser.text = "false"

    gae = options.find("globalAnnounceEnabled")
    if gae is not None:
        gae.text = "false"
    lae = options.find("localAnnounceEnabled")
    if lae is not None:
        lae.text = "false"

    for la in list(options.findall("listenAddress")):
        options.remove(la)
    la = ET.Element("listenAddress")
    la.text = f"tcp://0.0.0.0:{cfg['listen']}"
    options.append(la)

    ET.indent(tree, space="    ")
    tree.write(config_xml, encoding="utf-8")
print("OK")
PY
echo

echo "== Start server (Amvera-like) with allowlist =="
cat >"$BASE/sync-folders.server.yaml" <<'YAML'
folders:
  - id: test-sync
    label: test-sync
    type: sendreceive
    ignore_perms: true
    paths:
      amvera: /data/sync/test-sync
YAML

IDS="$(paste -sd, "$BASE/n1/device-id.txt" "$BASE/n2/device-id.txt" "$BASE/n3/device-id.txt")"
echo "AMVERA_ALLOWED_DEVICE_IDS: $IDS"

docker run -d \
  --name "$SERVER_NAME" \
  -p "${SERVER_PORT}:22000" \
  -p "${SERVER_BROWSER_PORT}:80" \
  -v "$BASE/server-data":/data \
  -v "$BASE/sync-folders.server.yaml":/app/sync-folders.yaml:ro \
  -e SYNC_CONFIG=/app/sync-folders.yaml \
  -e FILE_BROWSER_ENABLED=0 \
  -e AMVERA_ALLOWED_DEVICE_IDS="$IDS" \
  "$IMAGE" >/dev/null

for i in {1..30}; do
  if [[ -f "$BASE/server-data/syncthing/config/config.xml" ]]; then
    break
  fi
  sleep 1
  if [[ $i -eq 30 ]]; then
    echo "ERROR: server config.xml not created" >&2
    docker logs --tail 200 "$SERVER_NAME" >&2 || true
    exit 1
  fi
done

SERVER_ID="$(sed -n 's/.*<device id=\"\\([A-Z0-9-]\\+\\)\".*/\\1/p' "$BASE/server-data/syncthing/config/config.xml" | head -n 1)"
echo "Server Device ID: $SERVER_ID"
echo "$SERVER_ID" > "$BASE/server-device-id.txt"
echo

echo "== Configure n1/n2/n3 to connect to server =="
python3 - <<PY
import copy
import xml.etree.ElementTree as ET
from pathlib import Path

base = Path("$BASE")
server_id = Path("$BASE/server-device-id.txt").read_text().strip()
server_addr = "$SERVER_ADDR"

nodes = {
    "n1": base / "n1" / "home" / "config.xml",
    "n2": base / "n2" / "home" / "config.xml",
    "n3": base / "n3" / "home" / "config.xml",
}

for name, config_xml in nodes.items():
    tree = ET.parse(config_xml)
    root = tree.getroot()

    local_dev = root.find("device")
    local_id = local_dev.get("id") if local_dev is not None else ""
    if not local_id:
        raise SystemExit(f"Cannot determine local device id for {name}")

    defaults_device = root.find("defaults/device")
    defaults_folder = root.find("defaults/folder")
    if defaults_device is None or defaults_folder is None:
        raise SystemExit(f"Missing defaults templates for {name}")

    if not any((d.get("id") == server_id) for d in root.findall("device")):
        dev = copy.deepcopy(defaults_device)
        dev.set("id", server_id)
        dev.set("name", "amvera_srv")
        for addr in list(dev.findall("address")):
            dev.remove(addr)
        addr_el = ET.Element("address")
        addr_el.text = server_addr
        dev.append(addr_el)
        root.append(dev)

    folder_id = "test-sync"
    folder_path = str(base / name / "sync" / "test-sync")
    folder = None
    for f in root.findall("folder"):
        if f.get("id") == folder_id:
            folder = f
            break

    if folder is None:
        folder = copy.deepcopy(defaults_folder)
        folder.set("id", folder_id)
        folder.set("label", folder_id)
        folder.set("path", folder_path)
        folder.set("type", "sendreceive")
        folder.set("ignorePerms", "true")

        for d in list(folder.findall("device")):
            folder.remove(d)
        for did in (local_id, server_id):
            dev_el = ET.Element("device")
            dev_el.set("id", did)
            dev_el.set("introducedBy", "")
            enc_el = ET.Element("encryptionPassword")
            enc_el.text = ""
            dev_el.append(enc_el)
            folder.append(dev_el)
        root.append(folder)

    ET.indent(tree, space="    ")
    tree.write(config_xml, encoding="utf-8")
print("OK")
PY
echo

echo "== Start n1/n2/n3 =="
for n in n1 n2 n3; do
  HOME_DIR="$BASE/$n/home"
  LOG="$BASE/$n/syncthing.log"
  nohup syncthing serve --home "$HOME_DIR" --no-browser --no-restart >"$LOG" 2>&1 &
  echo $! > "$BASE/$n/pid"
  sleep 0.5
done
echo "PIDs:"
for n in n1 n2 n3; do
  echo "  $n $(cat "$BASE/$n/pid")"
done
echo

echo "== Create 3 files (one per node) and wait for sync =="
TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
for n in n1 n2 n3; do
  echo "file from $n @ $TS" > "$BASE/$n/sync/test-sync/from-$n.txt"
done
sync

SERVER_DIR="$BASE/server-data/sync/test-sync"
want=(from-n1.txt from-n2.txt from-n3.txt)

check_all() {
  for f in "${want[@]}"; do
    [[ -f "$BASE/n1/sync/test-sync/$f" ]] || return 1
    [[ -f "$BASE/n2/sync/test-sync/$f" ]] || return 1
    [[ -f "$BASE/n3/sync/test-sync/$f" ]] || return 1
    [[ -f "$SERVER_DIR/$f" ]] || return 1
  done
  return 0
}

for i in {1..60}; do
  if check_all; then
    echo "OK: all files present everywhere after $((i*2))s"
    break
  fi
  sleep 2
  if [[ $i -eq 60 ]]; then
    echo "ERROR: timeout waiting for sync" >&2
    ls -la "$SERVER_DIR" >&2 || true
    exit 1
  fi
done

echo
echo "== Summary =="
echo "Nodes GUI:"
echo "  n1 http://127.0.0.1:18384"
echo "  n2 http://127.0.0.1:18385"
echo "  n3 http://127.0.0.1:18386"
echo "Server sync port: 127.0.0.1:${SERVER_PORT}"
echo "Server Device ID: $SERVER_ID"
echo "Allowlist: $IDS"
echo
echo "Server files:"
ls -la "$SERVER_DIR" | rg 'from-' || true
echo
echo "Checksums (server):"
sha256sum "$SERVER_DIR"/from-n*.txt
echo
echo "Checksums (n1,n2,n3):"
sha256sum "$BASE"/n1/sync/test-sync/from-n*.txt
sha256sum "$BASE"/n2/sync/test-sync/from-n*.txt
sha256sum "$BASE"/n3/sync/test-sync/from-n*.txt
echo
echo "== Done =="
