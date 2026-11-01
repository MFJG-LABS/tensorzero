#!/usr/bin/env bash
# Uses only disposable containers on an internal network. No host ports or keys.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ $# != 2 ]]; then
  echo 'Usage: qualify-gateway.sh IMMUTABLE_IMAGE NEW_RECEIPT_DIRECTORY' >&2
  exit 2
fi
image="$1"
[[ "$image" =~ ^sha256:[0-9a-f]{64}$ || "$image" =~ ^[^[:space:]]+@sha256:[0-9a-f]{64}$ ]] || {
  echo 'Gateway image must be an immutable local image ID or registry digest.' >&2
  exit 2
}
# No implicit pull: image acquisition/build and host admission are separate steps.
docker image inspect "$image" >/dev/null
provider_image="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["synthetic_provider_image"])' "$here/baseline.json")"
docker image inspect "$provider_image" >/dev/null
mkdir "$2"
receipt="$(cd "$2" && pwd)"
prefix="mfjg-tz-parity-$(python3 -c 'import uuid; print(uuid.uuid4().hex)')"
network=""
provider=""
gateway=""
client=""
cleanup() {
  local status=$?
  local cleanup_failed=0
  trap - EXIT INT TERM
  if [[ -n "$gateway" ]]; then
    docker logs "$gateway" >"$receipt/gateway.log" 2>&1 || true
  fi
  for id in "$client" "$gateway" "$provider"; do
    if [[ -n "$id" ]] && ! docker rm -f "$id" >/dev/null 2>&1; then
      cleanup_failed=1
    fi
  done
  if [[ -n "$network" ]] && ! docker network rm "$network" >/dev/null 2>&1; then
    cleanup_failed=1
  fi
  python3 - "$status" "$cleanup_failed" "$network" "$client" "$gateway" "$provider" >"$receipt/cleanup.json" <<'PY'
import json, sys
status, failed, network, client, gateway, provider = sys.argv[1:]
print(json.dumps({'test_exit_status': int(status), 'cleanup_complete': failed == '0',
                  'network_id': network, 'container_ids': [client, gateway, provider]}))
PY
  if [[ "$status" == 0 && "$cleanup_failed" != 0 ]]; then
    echo "Synthetic test resources need cleanup; see $receipt/cleanup.json" >&2
    status=1
  fi
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
python3 "$here/synthetic_provider.py" --config >"$receipt/tensorzero.toml"
docker image inspect "$image" --format '{{json .Id}} {{json .Config.Labels}}' >"$receipt/image.txt"
network="$(docker network create --internal --label mfjg.purpose=synthetic-parity "$prefix")"
common=(--network "$network" --label mfjg.purpose=synthetic-parity --read-only --cap-drop ALL --security-opt no-new-privileges --pids-limit 128)
provider="$(docker create "${common[@]}" --name "$prefix-provider" --network-alias provider \
  --memory 128m --cpus 0.25 --user 65534:65534 \
  --mount "type=bind,source=$here,target=/work,readonly" \
  "$provider_image" python3 /work/synthetic_provider.py)"
gateway="$(docker create "${common[@]}" --name "$prefix-gateway" --network-alias gateway \
  --memory 1g --cpus 1 --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --mount "type=bind,source=$receipt/tensorzero.toml,target=/app/config/tensorzero.toml,readonly" \
  "$image" --config-file /app/config/tensorzero.toml)"
client="$(docker create "${common[@]}" --name "$prefix-client" --memory 128m --cpus 0.25 \
  --user 65534:65534 --mount "type=bind,source=$here,target=/work,readonly" \
  "$provider_image" python3 /work/contract_test.py)"
docker start "$provider" "$gateway" >/dev/null
docker start --attach "$client" >"$receipt/parity.json"
status="$(docker inspect "$client" --format '{{.State.ExitCode}}')"
[[ "$status" == 0 ]]
python3 -c 'import json,sys; r=json.load(open(sys.argv[1])); assert r["passed"] is True; print("Synthetic gateway parity passed:", len(r["checks"]), "checks")' "$receipt/parity.json"
