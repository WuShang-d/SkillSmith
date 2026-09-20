#!/usr/bin/env bash
set -euo pipefail

container_name="${VLLM_CONTAINER_NAME:-skillsmith-qwen36}"
port="${VLLM_PORT:-8000}"
attempts="${VLLM_READY_ATTEMPTS:-60}"

for ((attempt = 1; attempt <= attempts; attempt++)); do
  if curl --fail --silent --show-error "http://127.0.0.1:${port}/v1/models"; then
    echo
    echo "vLLM ready after ${attempt} check(s)."
    exit 0
  fi
  if ! docker inspect -f '{{.State.Running}}' "$container_name" 2>/dev/null | grep -qx true; then
    echo "vLLM container stopped before becoming ready." >&2
    docker logs --tail 120 "$container_name" >&2 || true
    exit 1
  fi
  sleep 10
done

echo "vLLM did not become ready within $((attempts * 10)) seconds." >&2
docker logs --tail 120 "$container_name" >&2 || true
exit 1
