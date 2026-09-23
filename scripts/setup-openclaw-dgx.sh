#!/usr/bin/env bash
# Install Node 24 + OpenClaw under ~/agent-tools and create an isolated
# OpenClaw profile that talks only to the loopback vLLM endpoint.
set -euo pipefail

tools="${AGENT_TOOLS_DIR:-$HOME/agent-tools}"
profile="${OPENCLAW_PROFILE:-skillsmith-eval}"
model="${OPENAI_MODEL:-Qwen/Qwen3.6-35B-A3B}"
base_url="${OPENAI_BASE_URL:-http://127.0.0.1:8000/v1}"
state="$HOME/.openclaw-$profile"

mkdir -p "$tools"
if [[ ! -x "$tools/node/bin/node" ]]; then
  version="$(curl -fsS https://nodejs.org/dist/index.json | python3 -c 'import json,sys; print(next(r["version"] for r in json.load(sys.stdin) if r["version"].startswith("v24.")))')"
  archive="node-$version-linux-arm64.tar.xz"
  (cd "$tools" && curl -fsSLO "https://nodejs.org/dist/$version/$archive" \
    && curl -fsSL "https://nodejs.org/dist/$version/SHASUMS256.txt" | grep " $archive\$" | sha256sum -c - \
    && tar xf "$archive" && ln -sfn "node-$version-linux-arm64" node)
fi
export PATH="$tools/node/bin:$tools/npm-global/bin:$PATH"
if ! command -v openclaw >/dev/null; then
  npm config set prefix "$tools/npm-global"
  npm config set fetch-retries 6
  npm install -g openclaw@latest --no-fund --no-audit
fi

mkdir -p "$state/workspace/skills"
cat > "$state/openclaw.json" <<JSON
{
  "models": {"providers": {"vllm": {
    "baseUrl": "$base_url", "apiKey": "\${VLLM_API_KEY}", "api": "openai-completions", "timeoutSeconds": 300,
    "models": [{"id": "$model", "name": "DGX local model", "reasoning": false, "input": ["text", "image"],
      "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0}, "contextWindow": 65536, "maxTokens": 4096}]
  }}},
  "agents": {"defaults": {"model": {"primary": "vllm/$model"}, "workspace": "$state/workspace", "thinkingDefault": "off"}}
}
JSON
openclaw --profile "$profile" config validate
echo "OpenClaw $(openclaw --version) ready. Before evaluating run:"
echo "  export PATH=\"$tools/node/bin:$tools/npm-global/bin:\$PATH\" VLLM_API_KEY=vllm-local"
