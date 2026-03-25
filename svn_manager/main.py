"""
SVNFree 主入口
"""
import sys
import os
import subprocess

# 确保包根路径在 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import (
    QApplication, QSystemTrayIcon, QMenu,
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QTextBrowser,
)
from PyQt6.QtGui import QIcon, QPixmap, QPainter, QColor, QFont
from PyQt6.QtCore import Qt, QSize

from svn_manager.ui.main_window import MainWindow


# ── SVN 检测 ─────────────────────────────────────────────────────────────────

_SVN_CANDIDATES = [
    "/opt/homebrew/bin/svn",
    "/usr/local/bin/svn",
    "/usr/bin/svn",
]


def _detect_svn() -> str | None:
    """返回找到的 svn 路径，未找到返回 None。"""
    for path in _SVN_CANDIDATES:
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    try:
        result = subprocess.run(
            ["which", "svn"], capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            found = result.stdout.strip()
            if found:
                return found
    except Exception:
        pass
    return None


class _SVNMissingDialog(QDialog):
    """svn CLI 未安装时的提示对话框。"""

    _STYLE = """
        QDialog { background: #1e1e2e; }
        QLabel#title {
            font-size: 18px; font-weight: 700; color: #f38ba8;
        }
        QLabel#sub {
            font-size: 13px; color: #cdd6f4;
        }
        QTextBrowser {
            background: #181825; color: #cdd6f4;
            border: 1px solid #313244; border-radius: 6px;
            font-family: "Menlo", "Monaco", monospace;
            font-size: 13px;
            padding: 10px;
            selection-background-color: #313244;
        }
        QPushButton#quitBtn {
            background: #f38ba8; color: #1e1e2e;
            font-size: 13px; font-weight: 600;
            border: none; border-radius: 6px;
            padding: 8px 28px;
        }
        QPushButton#quitBtn:hover { background: #eba0ac; }
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("SVNFree — 缺少依赖")
        self.setFixedSize(540, 420)
        self.setWindowFlag(Qt.WindowType.WindowCloseButtonHint, False)
        self.setStyleSheet(self._STYLE)
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(14)

        # 标题
        title = QLabel("未检测到 SVN 命令行工具")
        title.setObjectName("title")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # 说明
        sub = QLabel(
            "SVNFree 依赖系统安装的 <b>svn</b> 命令行工具，请按以下步骤安装后重新启动。"
        )
        sub.setObjectName("sub")
        sub.setWordWrap(True)
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(sub)

        # 安装说明
        guide = QTextBrowser()
        guide.setReadOnly(True)
        guide.setOpenExternalLinks(True)
        guide.setHtml("""
<p style="color:#a6e3a1; font-weight:600; margin:0 0 6px 0;">方法一：Homebrew 安装（推荐）</p>
<p style="margin:0 0 4px 0; color:#cdd6f4;">① 若未安装 Homebrew，先在终端执行：</p>
<pre style="background:#11111b; color:#cdd6f4; padding:6px 10px; border-radius:4px; margin:0 0 8px 0;">/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"</pre>
<p style="margin:0 0 4px 0; color:#cdd6f4;">② 安装 svn：</p>
<pre style="background:#11111b; color:#cdd6f4; padding:6px 10px; border-radius:4px; margin:0 0 12px 0;">brew install subversion</pre>

<p style="color:#89b4fa; font-weight:600; margin:0 0 6px 0;">方法二：Xcode Command Line Tools</p>
<p style="margin:0 0 4px 0; color:#cdd6f4;">在终端执行（svn 版本较旧，但无需 Homebrew）：</p>
<pre style="background:#11111b; color:#cdd6f4; padding:6px 10px; border-radius:4px; margin:0 0 12px 0;">xcode-select --install</pre>

<p style="color:#a6adc8; font-size:12px; margin:0;">
安装完成后，请<b style="color:#f9e2af;">重新启动 SVNFree</b>。
</p>
""")
        layout.addWidget(guide, 1)

        # 按钮行
        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        quit_btn = QPushButton("退出 SVNFree")
        quit_btn.setObjectName("quitBtn")
        quit_btn.setFixedHeight(36)
        quit_btn.clicked.connect(self.reject)
        btn_row.addWidget(quit_btn)
        layout.addLayout(btn_row)


def _create_tray_icon() -> QPixmap:
    """生成托盘图标"""
    pm = QPixmap(32, 32)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    # 背景圆
    painter.setBrush(QColor("#89b4fa"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(2, 2, 28, 28, 6, 6)
    # 文字
    painter.setPen(QColor("#1e1e2e"))
    font = QFont(".AppleSystemUIFont", 11, QFont.Weight.Bold)
    if not font.exactMatch():
        font = QFont("Helvetica Neue", 11, QFont.Weight.Bold)
    painter.setFont(font)
    painter.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, "SVN")
    painter.end()
    return pm


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("SVNFree")
    app.setApplicationDisplayName("SVNFree")
    app.setOrganizationName("SVNFree")
    app.setQuitOnLastWindowClosed(False)

    # macOS 下默认不显示菜单图标，强制开启
    app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)

    # macOS 风格
    app.setStyle("Fusion")

    # ── 启动前检测 svn CLI ──────────────────────────────────────────
    if _detect_svn() is None:
        dlg = _SVNMissingDialog()
        dlg.exec()          # 用户点"退出"后 reject() 关闭
        sys.exit(1)         # 强制退出，不进入主界面
    # ────────────────────────────────────────────────────────────────

    window = MainWindow()
    window.show()

    # 系统托盘
    tray = QSystemTrayIcon(app)
    tray_pm = _create_tray_icon()
    tray.setIcon(QIcon(tray_pm))
    tray.setToolTip("SVNFree — SVN 管理器")

    tray_menu = QMenu()
    show_act = tray_menu.addAction("显示主窗口")
    show_act.triggered.connect(lambda: (window.show(), window.raise_()))
    tray_menu.addSeparator()
    quit_act = tray_menu.addAction("退出")
    quit_act.triggered.connect(app.quit)
    tray.setContextMenu(tray_menu)
    tray.activated.connect(
        lambda reason: (window.show(), window.raise_())
        if reason == QSystemTrayIcon.ActivationReason.Trigger else None
    )
    tray.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
