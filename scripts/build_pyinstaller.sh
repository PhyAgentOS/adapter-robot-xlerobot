#!/usr/bin/env bash

set -euo pipefail

# 打包 XLeRobot 节点为单文件可执行程序。
# 产物在本包 dist/robots_xlerobot，中间文件在本包 build/pyinstaller/。
# 脚本会创建隔离的局部构建虚拟环境，不依赖当前 shell 的 Python 环境。

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGE_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DIST_DIR="${PACKAGE_DIR}/dist"
WORK_DIR="${PACKAGE_DIR}/build/pyinstaller"
VENV_DIR="${PACKAGE_DIR}/.venv_build"

cd "${PACKAGE_DIR}"
mkdir -p "${DIST_DIR}" "${WORK_DIR}"
rm -f "${DIST_DIR}/robots_xlerobot" "${DIST_DIR}/robots_xlerobot.exe"
rm -rf "${VENV_DIR}"
trap 'rm -rf "${VENV_DIR}"' EXIT

echo "==> [robots_xlerobot] 正在同步锁定的隔离构建环境..."
UV_PROJECT_ENVIRONMENT="${VENV_DIR}" uv sync \
  --project "${PACKAGE_DIR}" \
  --frozen \
  --no-dev \
  --extra pyinstaller \
  --python 3.12

echo "==> [robots_xlerobot] 开始使用 PyInstaller 进行打包..."
"${VENV_DIR}/bin/pyinstaller" \
  --noconfirm \
  --clean \
  --distpath "${DIST_DIR}" \
  --workpath "${WORK_DIR}" \
  "${SCRIPT_DIR}/robots_xlerobot.spec"

EXE_NAME="robots_xlerobot"
if [[ -f "${DIST_DIR}/${EXE_NAME}" ]]; then
  echo "OK: ${DIST_DIR}/${EXE_NAME}"
elif [[ -f "${DIST_DIR}/${EXE_NAME}.exe" ]]; then
  echo "OK: ${DIST_DIR}/${EXE_NAME}.exe"
else
  echo "WARNING: ${DIST_DIR}/${EXE_NAME} 未找到，请检查 PyInstaller 输出。" >&2
  exit 1
fi
