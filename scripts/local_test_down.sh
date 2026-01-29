#!/usr/bin/env bash
set -euo pipefail

BASE="/tmp/syncthing-local-test"
SERVER_NAME="amvera_srv_test"

echo "== Local test cleanup =="

if command -v docker >/dev/null 2>&1; then
  if docker ps -a --format '{{.Names}}' | grep -qx "$SERVER_NAME"; then
    echo "Stopping container: $SERVER_NAME"
    docker rm -f "$SERVER_NAME" >/dev/null || true
  fi
fi

if [[ -d "$BASE" ]]; then
  echo "Stopping syncthing nodes"
  for n in n1 n2 n3; do
    if [[ -f "$BASE/$n/pid" ]]; then
      pid="$(cat "$BASE/$n/pid" || true)"
      if [[ -n "${pid:-}" ]]; then
        kill "$pid" >/dev/null 2>&1 || true
      fi
    fi
  done
fi

sleep 1

echo "Removing test files: $BASE"
rm -rf "$BASE"

echo "== Done =="
