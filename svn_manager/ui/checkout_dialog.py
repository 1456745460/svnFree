"""
检出对话框 - 支持实时日志输出
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFileDialog, QFormLayout,
    QComboBox, QTextEdit, QProgressBar,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from .theme import MAIN_STYLE


class CheckoutWorker(QThread):
    """后台检出线程，逐行回传日志"""
    log_line = pyqtSignal(str)       # 每收到一行
    finished = pyqtSignal(bool, str) # 完成(ok, full_output)

    def __init__(self, engine, url: str, path: str, revision: str,
                 depth: str, username: str, password: str,
                 no_auth_cache: bool):
        super().__init__()
        self.engine = engine
        self.url = url
        self.path = path
        self.revision = revision
        self.depth = depth
        self.username = username
        self.password = password
        self.no_auth_cache = no_auth_cache

    def run(self):
        ok, out = self.engine.checkout(
            url=self.url,
            path=self.path,
            revision=self.revision,
            depth=self.depth,
            username=self.username or None,
            password=self.password or None,
            no_auth_cache=self.no_auth_cache,
            line_callback=lambda line: self.log_line.emit(line),
        )
        self.finished.emit(ok, out)


class CheckoutDialog(QDialog):
    # 检出成功后向外传递 (url, path)
    checkout_success = pyqtSignal(str, str)

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self._worker = None
        self._done = False          # 是否已完成检出
        self.setWindowTitle("检出仓库")
        self.setMinimumWidth(560)
        self.setMinimumHeight(460)
        self.setStyleSheet(MAIN_STYLE)
        self._setup_ui()

    # ── UI 构建 ────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title = QLabel("检出 SVN 仓库")
        title.setStyleSheet("font-size:15px;font-weight:700;color:#89b4fa;")
        layout.addWidget(title)

        # ── 参数表单 ──
        form = QFormLayout()
        form.setSpacing(10)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("https://svn.example.com/repos/project")
        form.addRow("仓库 URL：", self.url_edit)

        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("选择本地目录...")
        browse_btn = QPushButton("浏览...")
        browse_btn.setFixedWidth(70)
        browse_btn.clicked.connect(self._browse)
        path_row.addWidget(self.path_edit)
        path_row.addWidget(browse_btn)
        form.addRow("本地路径：", path_row)

        self.rev_edit = QLineEdit("HEAD")
        form.addRow("版本号：", self.rev_edit)

        self.depth_combo = QComboBox()
        for depth, label in [
            ("infinity",   "完整（infinity）"),
            ("immediates", "仅目录（immediates）"),
            ("files",      "仅文件（files）"),
            ("empty",      "空（empty）"),
        ]:
            self.depth_combo.addItem(label, depth)
        form.addRow("检出深度：", self.depth_combo)

        layout.addLayout(form)

        # ── 进度条 ──
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)   # 不确定进度，滚动样式
        self.progress.setFixedHeight(4)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)

        # ── 日志输出 ──
        log_label = QLabel("检出日志：")
        log_label.setStyleSheet("font-size:12px;color:#a6adc8;")
        layout.addWidget(log_label)

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(160)
        self.log_view.setPlaceholderText("点击「检出」后，实时日志将显示在这里...")
        self.log_view.setStyleSheet(
            "background:#111117;color:#cdd6f4;"
            "border:1px solid #313244;border-radius:4px;"
            "font-size:12px;font-family:monospace;"
        )
        layout.addWidget(self.log_view, 1)

        # ── 按钮行 ──
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setFixedSize(80, 34)
        self.cancel_btn.clicked.connect(self._on_cancel)
        btn_row.addWidget(self.cancel_btn)

        self.checkout_btn = QPushButton("检出")
        self.checkout_btn.setObjectName("primaryBtn")
        self.checkout_btn.setFixedSize(80, 34)
        self.checkout_btn.clicked.connect(self._start_checkout)
        btn_row.addWidget(self.checkout_btn)
        layout.addLayout(btn_row)

    # ── 事件处理 ───────────────────────────────────────────────────

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "选择检出目录")
        if path:
            self.path_edit.setText(path)

    def _start_checkout(self):
        url = self.url_edit.text().strip()
        path = self.path_edit.text().strip()
        rev = self.rev_edit.text().strip() or "HEAD"
        depth = self.depth_combo.currentData()

        if not url:
            self._append_log("✗ 请填写仓库 URL")
            return
        if not path:
            self._append_log("✗ 请选择本地路径")
            return

        # 检查是否需要认证（先弹出认证对话框询问，或让用户留空跳过）
        username, password, no_cache = self._ask_credentials_if_needed()
        # 若用户关闭了认证对话框且 URL 含认证信息则继续（no_auth_cache=False）

        self._set_running(True)
        self.log_view.clear()
        self._append_log(f"正在检出: {url}")
        self._append_log(f"本地路径: {path}\n")

        self._worker = CheckoutWorker(
            engine=self.engine,
            url=url, path=path,
            revision=rev, depth=depth,
            username=username, password=password,
            no_auth_cache=no_cache,
        )
        self._worker.log_line.connect(self._append_log)
        self._worker.finished.connect(self._on_finished)
        self._worker.start()

    def _ask_credentials_if_needed(self) -> tuple[str, str, bool]:
        """弹出可选的认证对话框，允许用户预先填写凭证（也可跳过）"""
        # 此处直接返回空，由 _on_finished 检测到认证错误时再弹窗重试
        return "", "", False

    def _on_cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(2000)
            self._append_log("\n[已取消]")
            self._set_running(False)
        else:
            self.reject()

    def _on_finished(self, ok: bool, output: str):
        self._set_running(False)
        self._done = ok

        if ok:
            self._append_log("\n✓ 检出完成！")
            self.checkout_btn.setText("关闭")
            self.checkout_btn.clicked.disconnect()
            self.checkout_btn.clicked.connect(self.accept)
            url = self.url_edit.text().strip()
            path = self.path_edit.text().strip()
            self.checkout_success.emit(url, path)
        else:
            # 检测是否为认证错误
            auth_keywords = [
                "authentication", "authorization", "E170001",
                "credentials", "password", "username",
                "realm", "forbidden", "401", "403",
            ]
            lower_out = output.lower()
            is_auth_error = any(k in lower_out for k in auth_keywords)

            if is_auth_error:
                self._append_log("\n⚠ 需要身份验证，请输入凭证后重试...")
                self._prompt_auth_retry()
            else:
                self._append_log("\n✗ 检出失败")

    def _prompt_auth_retry(self):
        """弹出认证对话框，重新发起检出"""
        from .auth_dialog import AuthDialog

        # 尝试从输出中提取 realm 信息
        realm = ""
        for line in self.log_view.toPlainText().splitlines():
            if "realm" in line.lower() or "authentication realm" in line.lower():
                realm = line.strip()
                break
            if "svn" in line.lower() and ("http" in line.lower() or "svn://" in line.lower()):
                realm = line.strip()
                break

        dlg = AuthDialog(realm=realm, parent=self)
        if dlg.exec():
            username, password, no_cache = dlg.get_credentials()
            if not username:
                self._append_log("✗ 未填写用户名，放弃重试")
                return
            # 重新发起检出
            url = self.url_edit.text().strip()
            path = self.path_edit.text().strip()
            rev = self.rev_edit.text().strip() or "HEAD"
            depth = self.depth_combo.currentData()

            self._set_running(True)
            self._append_log(f"\n--- 使用凭证重试 ---\n")

            self._worker = CheckoutWorker(
                engine=self.engine,
                url=url, path=path,
                revision=rev, depth=depth,
                username=username, password=password,
                no_auth_cache=no_cache,
            )
            self._worker.log_line.connect(self._append_log)
            self._worker.finished.connect(self._on_finished)
            self._worker.start()
        else:
            self._append_log("✗ 已取消认证")

    # ── 辅助 ───────────────────────────────────────────────────────

    def _append_log(self, line: str):
        """追加日志行并自动滚动到底部"""
        self.log_view.append(line)
        sb = self.log_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _set_running(self, running: bool):
        self.progress.setVisible(running)
        self.checkout_btn.setEnabled(not running)
        self.url_edit.setEnabled(not running)
        self.path_edit.setEnabled(not running)
        self.rev_edit.setEnabled(not running)
        self.depth_combo.setEnabled(not running)

    def get_result(self) -> tuple[str, str, str]:
        """兼容旧接口"""
        url = self.url_edit.text().strip()
        path = self.path_edit.text().strip()
        rev = self.rev_edit.text().strip() or "HEAD"
        return url, path, rev
