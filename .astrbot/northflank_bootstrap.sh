#!/usr/bin/env bash
# Bootstrap AstrBot on a stock soulter/astrbot container (Northflank).
# - installs huggingface_hub
# - restores data/ from private HF dataset
# - renders config from env secrets
# - syncs state back every 5 minutes
# - starts AstrBot
set -euo pipefail

export ASTRBOT_ROOT="${ASTRBOT_ROOT:-/AstrBot}"
REPO_RAW="${CF_REPO_RAW:-https://raw.githubusercontent.com/valdislavn-spec/content-factory/main/.astrbot}"
WORK=/opt/cf
mkdir -p "$WORK" "$ASTRBOT_ROOT/data/config" "$ASTRBOT_ROOT/data/plugins" "$ASTRBOT_ROOT/data/temp"

python -m pip install --no-cache-dir -q huggingface_hub

for f in state_sync.py render_config_image.py cmd_config.template.json; do
  curl -fsSL "$REPO_RAW/$f" -o "$WORK/$f"
done

export ASTRBOT_TEMPLATE="$WORK/cmd_config.template.json"
python "$WORK/state_sync.py" restore || true
python "$WORK/render_config_image.py"

(
  while true; do
    sleep 300
    python "$WORK/state_sync.py" save >/dev/null 2>&1 || true
  done
) &

exec python main.py
