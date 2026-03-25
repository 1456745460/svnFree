"""
更新对话框 - 支持认证失败时自动弹出用户名/密码输入
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QProgressBar, QLineEdit,
    QFormLayout,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from .theme import MAIN_STYLE
from ..core.svn_engine import SVNEngine

# 认证错误关键字（小写匹配）
_AUTH_KEYWORDS = [
    "authentication", "authorization", "e170001",
    "no authentication provider", "credentials",
    "password", "username", "realm", "forbidden", "401", "403",
]


def _is_auth_error(msg: str) -> bool:
    low = msg.lower()
    return any(k in low for k in _AUTH_KEYWORDS)


class UpdateWorker(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, engine: SVNEngine, path: str, revision: str,
                 username: str = None, password: str = None,
                 no_auth_cache: bool = False):
        super().__init__()
        self.engine = engine
        self.path = path
        self.revision = revision
        self.username = username
        self.password = password
        self.no_auth_cache = no_auth_cache

    def run(self):
        ok, msg = self.engine.update(
            self.path,
            revision=self.revision,
            username=self.username,
            password=self.password,
            no_auth_cache=self.no_auth_cache,
        )
        self.finished.emit(ok, msg)


class UpdateDialog(QDialog):
    def __init__(self, engine: SVNEngine, path: str, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.path = path
        self._worker = None
        self.setWindowTitle("更新工作副本")
        self.setMinimumWidth(480)
        self.setStyleSheet(MAIN_STYLE)
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel(f"更新: {self.path}")
        title.setStyleSheet("font-size:12px;color:#89b4fa;")
        title.setWordWrap(True)
        layout.addWidget(title)

        form = QFormLayout()
        self.rev_edit = QLineEdit("HEAD")
        form.addRow("更新到版本：", self.rev_edit)
        layout.addLayout(form)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setFixedHeight(4)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setMinimumHeight(120)
        self.output.setPlaceholderText("更新输出将显示在这里...")
        self.output.setStyleSheet(
            "background:#111117;color:#cdd6f4;border:1px solid #313244;"
            "border-radius:4px;font-size:12px;font-family:monospace;")
        layout.addWidget(self.output)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.close_btn = QPushButton("关闭")
        self.close_btn.setFixedSize(80, 32)
        self.close_btn.clicked.connect(self.accept)
        btn_row.addWidget(self.close_btn)
        self.update_btn = QPushButton("开始更新")
        self.update_btn.setObjectName("primaryBtn")
        self.update_btn.setFixedSize(96, 32)
        self.update_btn.clicked.connect(self._start_update)
        btn_row.addWidget(self.update_btn)
        layout.addLayout(btn_row)

    def _start_update(self, username: str = None, password: str = None,
                      no_auth_cache: bool = False):
        rev = self.rev_edit.text().strip() or "HEAD"
        self.update_btn.setEnabled(False)
        self.rev_edit.setEnabled(False)
        self.progress.setVisible(True)
        self.output.clear()
        self.output.append(f"正在更新到版本 {rev}...")
        self._worker = UpdateWorker(
            self.engine, self.path, rev,
            username=username, password=password,
            no_auth_cache=no_auth_cache,
        )
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    # 保持旧槽名兼容（被 clicked 连接）
    _do_update = _start_update

    def _on_done(self, ok: bool, msg: str):
        self.progress.setVisible(False)
        self.update_btn.setEnabled(True)
        self.rev_edit.setEnabled(True)
        self.output.append(msg)
        if ok:
            self.output.append("\n✓ 更新完成")
        else:
            self.output.append("\n✗ 更新失败")
            if _is_auth_error(msg):
                self._prompt_auth_retry()

    def _prompt_auth_retry(self):
        from .auth_dialog import AuthDialog
        self.output.append("\n⚠ 检测到认证错误，请输入用户名密码重试...")
        dlg = AuthDialog(parent=self)
        if dlg.exec():
            username, password, no_cache = dlg.get_credentials()
            if username:
                self._start_update(username=username, password=password,
                                   no_auth_cache=no_cache)
            else:
                self.output.append("✗ 未填写用户名，放弃重试")
        else:
            self.output.append("✗ 已取消认证")
