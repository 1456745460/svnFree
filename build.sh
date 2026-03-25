#!/bin/bash
# SVNFree 打包脚本
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="$SCRIPT_DIR/venv/bin/python3"
DIST_DIR="$SCRIPT_DIR/dist"
BUILD_DIR="$SCRIPT_DIR/build"
APP_NAME="SVNFree"

cd "$SCRIPT_DIR"

echo "========================================"
echo "  SVNFree 打包脚本"
echo "========================================"
echo ""

# ── 1. 检查 venv ──────────────────────────────────────────────────────────────
if [ ! -f "$VENV_PYTHON" ]; then
    echo "[1/4] 创建虚拟环境..."
    python3 -m venv venv
    "$VENV_PYTHON" -m pip install --upgrade pip -q
    "$VENV_PYTHON" -m pip install PyQt6 watchdog pillow pyinstaller -q
    echo "      虚拟环境创建完成"
else
    echo "[1/4] 虚拟环境已存在，跳过"
fi

# ── 2. 检查 pyinstaller ───────────────────────────────────────────────────────
if ! "$VENV_PYTHON" -m PyInstaller --version &>/dev/null; then
    echo "[2/4] 安装 PyInstaller..."
    "$VENV_PYTHON" -m pip install pyinstaller -q
else
    echo "[2/4] PyInstaller 已就绪：$("$VENV_PYTHON" -m PyInstaller --version)"
fi

# ── 3. 清理旧产物 ─────────────────────────────────────────────────────────────
echo "[3/4] 清理旧打包产物..."
rm -rf "$DIST_DIR/$APP_NAME.app" "$DIST_DIR/$APP_NAME" "$BUILD_DIR"

# ── 4. 执行打包 ───────────────────────────────────────────────────────────────
echo "[4/4] 开始打包..."
echo ""
"$VENV_PYTHON" -m PyInstaller SVNFree.spec --noconfirm

# ── 完成 ──────────────────────────────────────────────────────────────────────
APP_PATH="$DIST_DIR/$APP_NAME.app"
if [ -d "$APP_PATH" ]; then
    SIZE=$(du -sh "$APP_PATH" | cut -f1)
    echo ""
    echo "========================================"
    echo "  打包成功！"
    echo "  路径：$APP_PATH"
    echo "  大小：$SIZE"
    echo "========================================"
    echo ""
    # 在 Finder 中显示
    open -R "$APP_PATH"
else
    echo ""
    echo "[错误] 打包失败，未找到 $APP_PATH"
    exit 1
fi
