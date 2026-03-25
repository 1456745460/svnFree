"""
提交对话框
"""
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTextEdit, QTreeWidget, QTreeWidgetItem,
    QHeaderView, QSplitter, QCheckBox, QProgressBar,
    QFrame, QMessageBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QBrush

from ..core.svn_engine import SVNEngine, SVNFileStatus, SVNStatus
from .theme import MAIN_STYLE, STATUS_COLORS, STATUS_LABELS

# 认证错误关键字（小写匹配）
_AUTH_KEYWORDS = [
    "authentication", "authorization", "e170001",
    "no authentication provider", "credentials",
    "password", "username", "realm", "forbidden", "401", "403",
]


def _is_auth_error(msg: str) -> bool:
    low = msg.lower()
    return any(k in low for k in _AUTH_KEYWORDS)


class CommitWorker(QThread):
    finished = pyqtSignal(bool, str)

    def __init__(self, engine, paths, message,
                 username: str = None, password: str = None,
                 no_auth_cache: bool = False):
        super().__init__()
        self.engine = engine
        self.paths = paths
        self.message = message
        self.username = username
        self.password = password
        self.no_auth_cache = no_auth_cache

    def run(self):
        ok, msg = self.engine.commit(
            self.paths, self.message,
            username=self.username,
            password=self.password,
            no_auth_cache=self.no_auth_cache,
        )
        self.finished.emit(ok, msg)


class CommitDialog(QDialog):
    def __init__(self, engine: SVNEngine, wc_path: str,
                 changed_files: list[SVNFileStatus], parent=None):
        super().__init__(parent)
        self.engine = engine
        self.wc_path = wc_path
        self.changed_files = changed_files
        self._worker = None
        self.setWindowTitle("提交更改")
        self.setMinimumSize(760, 540)
        self.resize(880, 620)
        self.setStyleSheet(MAIN_STYLE)
        self._setup_ui()
        self._populate_files()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel(f"工作副本: {self.wc_path}")
        title.setStyleSheet("font-size:12px;color:#89b4fa;")
        title.setWordWrap(True)
        layout.addWidget(title)

        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter, 1)

        # 提交说明
        msg_w = QFrame()
        ml = QVBoxLayout(msg_w)
        ml.setContentsMargins(0, 0, 0, 0)
        ml.setSpacing(4)
        ml.addWidget(QLabel("提交说明："))
        self.message_edit = QTextEdit()
        self.message_edit.setPlaceholderText("请输入提交说明...")
        ml.addWidget(self.message_edit)
        splitter.addWidget(msg_w)

        # 文件列表
        files_w = QFrame()
        fl = QVBoxLayout(files_w)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(4)
        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("变更文件："))
        hdr.addStretch()
        self.select_all_cb = QCheckBox("全选")
        self.select_all_cb.setChecked(True)
        self.select_all_cb.toggled.connect(self._toggle_all)
        hdr.addWidget(self.select_all_cb)
        fl.addLayout(hdr)

        self.file_list = QTreeWidget()
        self.file_list.setHeaderLabels(["", "状态", "文件路径"])
        self.file_list.setRootIsDecorated(False)
        self.file_list.setAlternatingRowColors(True)
        h = self.file_list.header()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.file_list.setColumnWidth(0, 30)
        self.file_list.setColumnWidth(1, 80)
        fl.addWidget(self.file_list)
        splitter.addWidget(files_w)
        splitter.setSizes([160, 280])

        # 进度
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setFixedHeight(4)
        layout.addWidget(self.progress_bar)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color:#a6adc8;font-size:12px;")
        layout.addWidget(self.status_label)

        # 按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setFixedSize(88, 36)
        self.cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self.cancel_btn)
        self.commit_btn = QPushButton("提交")
        self.commit_btn.setObjectName("primaryBtn")
        self.commit_btn.setFixedSize(88, 36)
        self.commit_btn.clicked.connect(self._do_commit)
        btn_row.addWidget(self.commit_btn)
        layout.addLayout(btn_row)

    def _populate_files(self):
        STATUS_ICON = {
            SVNStatus.MODIFIED: "M", SVNStatus.ADDED: "A",
            SVNStatus.DELETED: "D", SVNStatus.CONFLICTED: "C",
            SVNStatus.UNVERSIONED: "?", SVNStatus.MISSING: "!",
            SVNStatus.REPLACED: "R",
        }
        for fs in self.changed_files:
            item = QTreeWidgetItem()
            item.setCheckState(0, Qt.CheckState.Checked)
            status_word = fs.status.value
            char = STATUS_ICON.get(fs.status, "?")
            color = STATUS_COLORS.get(status_word, "#cdd6f4")
            item.setText(1, f" {char}  {STATUS_LABELS.get(status_word, status_word)}")
            item.setForeground(1, QBrush(QColor(color)))
            rel = os.path.relpath(fs.path, self.wc_path)
            item.setText(2, rel)
            item.setToolTip(2, fs.path)
            item.setData(0, Qt.ItemDataRole.UserRole, fs.path)
            self.file_list.addTopLevelItem(item)

    def _toggle_all(self, checked: bool):
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self.file_list.topLevelItemCount()):
            self.file_list.topLevelItem(i).setCheckState(0, state)

    def _get_selected_paths(self) -> list[str]:
        paths = []
        for i in range(self.file_list.topLevelItemCount()):
            item = self.file_list.topLevelItem(i)
            if item.checkState(0) == Qt.CheckState.Checked:
                p = item.data(0, Qt.ItemDataRole.UserRole)
                if p:
                    paths.append(p)
        return paths

    def _do_commit(self, username: str = None, password: str = None,
                   no_auth_cache: bool = False):
        message = self.message_edit.toPlainText().strip()
        if not message:
            QMessageBox.warning(self, "提交", "请填写提交说明。")
            return
        paths = self._get_selected_paths()
        if not paths:
            QMessageBox.warning(self, "提交", "请至少选择一个文件。")
            return
        self.commit_btn.setEnabled(False)
        self.cancel_btn.setEnabled(False)
        self.progress_bar.setVisible(True)
        self.status_label.setText("正在提交...")
        self._worker = CommitWorker(
            self.engine, paths, message,
            username=username, password=password,
            no_auth_cache=no_auth_cache,
        )
        self._worker.finished.connect(self._on_commit_done)
        self._worker.start()

    def _on_commit_done(self, ok: bool, msg: str):
        self.progress_bar.setVisible(False)
        self.commit_btn.setEnabled(True)
        self.cancel_btn.setEnabled(True)
        if ok:
            self.status_label.setText("✓ 提交成功")
            QMessageBox.information(self, "提交成功", msg or "提交成功！")
            self.accept()
        else:
            self.status_label.setText("✗ 提交失败")
            if _is_auth_error(msg):
                self._prompt_auth_retry(msg)
            else:
                QMessageBox.critical(self, "提交失败", msg)

    def _prompt_auth_retry(self, err_msg: str = ""):
        from .auth_dialog import AuthDialog
        self.status_label.setText("⚠ 需要身份验证，请输入凭证后重试")
        dlg = AuthDialog(parent=self)
        if dlg.exec():
            username, password, no_cache = dlg.get_credentials()
            if username:
                self._do_commit(username=username, password=password,
                                no_auth_cache=no_cache)
            else:
                self.status_label.setText("✗ 未填写用户名，放弃重试")
                QMessageBox.critical(self, "提交失败", err_msg)
        else:
            self.status_label.setText("✗ 已取消认证")
            QMessageBox.critical(self, "提交失败", err_msg)
