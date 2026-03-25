#!/bin/bash
# SVNFree 启动脚本
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python3"

if [ ! -f "$VENV_PYTHON" ]; then
    echo "正在初始化虚拟环境..."
    python3 -m venv "$SCRIPT_DIR/venv"
    "$VENV_PYTHON" -m pip install --upgrade pip -q
    "$VENV_PYTHON" -m pip install PyQt6 watchdog pillow pyinstaller -q
    echo "初始化完成"
fi

exec "$VENV_PYTHON" "$SCRIPT_DIR/svn_manager/main.py" "$@"
