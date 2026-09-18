#!/usr/bin/env bash
# 历史导入工具：从外部 Xlerobot 资产源仅导入 *.glb 到 assets/glb/。
# 当前交付资产已落盘到本仓；常规开发、CI 与仿真示例不再需要运行本脚本。
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEFAULT_SRC="$(cd "$ROOT/../.." && pwd)/robot-mj-model/models/Xlerobot"
SRC="${XLEROBOT_MJCF_SRC:-$DEFAULT_SRC}"
DST="$ROOT/assets/glb"

if [[ ! -d "$SRC" ]]; then
  echo "Source not found: $SRC" >&2
  echo "Set XLEROBOT_MJCF_SRC to your robot-mj-model/models/Xlerobot path." >&2
  exit 1
fi

mkdir -p "$DST"
n=0
while IFS= read -r -d '' f; do
  rel="${f#"$SRC"/}"
  out="$DST/$rel"
  mkdir -p "$(dirname "$out")"
  cp -v "$f" "$out"
  n=$((n + 1))
done < <(find "$SRC" -type f -name '*.glb' -print0)

if [[ "$n" -eq 0 ]]; then
  echo "No .glb files under: $SRC"
  exit 0
fi
echo "Copied $n GLB file(s) to: $DST"
