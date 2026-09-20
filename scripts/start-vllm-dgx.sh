#!/usr/bin/env bash
set -euo pipefail

image="${VLLM_IMAGE:-vllm/vllm-openai:v0.28.0}"
model_path="${MODEL_PATH:-/home/xsuper/models/Qwen3.6-35B-A3B}"
served_name="${SERVED_MODEL_NAME:-Qwen/Qwen3.6-35B-A3B}"
container_name="${VLLM_CONTAINER_NAME:-skillsmith-qwen36}"
port="${VLLM_PORT:-8000}"
memory_utilization="${VLLM_GPU_MEMORY_UTILIZATION:-0.75}"

if [[ ! -d "$model_path" ]]; then
  echo "Model directory not found: $model_path" >&2
  exit 1
fi

if docker inspect "$container_name" >/dev/null 2>&1; then
  if [[ "$(docker inspect -f '{{.State.Running}}' "$container_name")" == "true" ]]; then
    echo "vLLM container is already running: $container_name"
    exit 0
  fi
  docker rm "$container_name" >/dev/null
fi

docker run -d \
  --name "$container_name" \
  --restart unless-stopped \
  --gpus all \
  --ipc=host \
  -p "127.0.0.1:${port}:8000" \
  -e VLLM_USE_DEEP_GEMM=0 \
  -v "${model_path}:/model:ro" \
  "$image" \
  --model /model \
  --served-model-name "$served_name" \
  --host 0.0.0.0 \
  --port 8000 \
  --tensor-parallel-size 1 \
  --trust-remote-code \
  --gpu-memory-utilization "$memory_utilization" \
  --max-model-len 16384 \
  --max-num-seqs 1 \
  --max-num-batched-tokens 4096 \
  --enable-chunked-prefill \
  --enable-prefix-caching \
  --moe-backend triton

echo "Started $container_name. Follow startup with:"
echo "  docker logs -f $container_name"
echo "Readiness endpoint: http://127.0.0.1:${port}/v1/models"
