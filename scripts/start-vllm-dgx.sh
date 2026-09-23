#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${VLLM_IMAGE:-}" ]]; then
  image="$VLLM_IMAGE"
elif docker image inspect vllm/vllm-openai:v0.28.0 >/dev/null 2>&1; then
  image="vllm/vllm-openai:v0.28.0"
elif docker image inspect vllm/vllm-openai:latest >/dev/null 2>&1; then
  image="vllm/vllm-openai:latest"
else
  image="vllm/vllm-openai:v0.28.0"
fi
model_path="${MODEL_PATH:-/home/xsuper/models/Qwen3.6-35B-A3B}"
served_name="${SERVED_MODEL_NAME:-Qwen/Qwen3.6-35B-A3B}"
container_name="${VLLM_CONTAINER_NAME:-skillsmith-qwen36}"
port="${VLLM_PORT:-8000}"
memory_utilization="${VLLM_GPU_MEMORY_UTILIZATION:-0.75}"
max_model_len="${VLLM_MAX_MODEL_LEN:-65536}"
# Agent harnesses (trigger evaluation, OpenClaw) need OpenAI-style tool calls.
tool_parser="${VLLM_TOOL_CALL_PARSER:-qwen3_coder}"
reasoning_parser="${VLLM_REASONING_PARSER:-qwen3}"

if [[ ! -d "$model_path" ]]; then
  echo "Model directory not found: $model_path" >&2
  exit 1
fi

if docker inspect "$container_name" >/dev/null 2>&1; then
  if [[ "${VLLM_RECREATE:-0}" != "1" && "$(docker inspect -f '{{.State.Running}}' "$container_name")" == "true" ]]; then
    echo "vLLM container is already running: $container_name (set VLLM_RECREATE=1 to apply new flags)"
    exit 0
  fi
  docker rm -f "$container_name" >/dev/null
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
  /model \
  --served-model-name "$served_name" \
  --host 0.0.0.0 \
  --port 8000 \
  --tensor-parallel-size 1 \
  --trust-remote-code \
  --gpu-memory-utilization "$memory_utilization" \
  --max-model-len "$max_model_len" \
  --max-num-seqs 1 \
  --max-num-batched-tokens 4096 \
  --enable-chunked-prefill \
  --enable-prefix-caching \
  --moe-backend triton \
  --enable-auto-tool-choice \
  --tool-call-parser "$tool_parser" \
  --reasoning-parser "$reasoning_parser"

echo "Started $container_name. Follow startup with:"
echo "  docker logs -f $container_name"
echo "Readiness endpoint: http://127.0.0.1:${port}/v1/models"
