"""
日志对话框
"""
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTreeWidget, QTreeWidgetItem,
    QSplitter, QTextEdit, QHeaderView, QFrame,
    QSpinBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QBrush

from ..core.svn_engine import SVNEngine, SVNLogEntry
from .theme import MAIN_STYLE
from .diff_viewer import DiffViewer
from ..utils.helpers import format_date


class LogWorker(QThread):
    finished = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, engine: SVNEngine, path: str, limit: int):
        super().__init__()
        self.engine = engine
        self.path = path
        self.limit = limit

    def run(self):
        try:
            entries = self.engine.get_log(
                self.path, limit=self.limit, verbose=True)
            self.finished.emit(entries)
        except Exception as e:
            self.error.emit(str(e))


class DiffWorker(QThread):
    """后台获取 diff 内容"""
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, engine: SVNEngine, path: str, revision: str,
                 repo_file_path: str = None):
        super().__init__()
        self.engine = engine
        self.path = path
        self.revision = revision
        self.repo_file_path = repo_file_path

    def run(self):
        try:
            diff = self.engine.get_diff_for_revision(
                self.path, self.revision, self.repo_file_path)
            self.finished.emit(diff)
        except Exception as e:
            self.error.emit(str(e))


class LogDialog(QDialog):
    def __init__(self, engine: SVNEngine, path: str, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.path = path
        self._worker = None
        self._diff_worker = None
        self._current_entry: SVNLogEntry = None
        self.setWindowTitle(f"提交日志 — {os.path.basename(path)}")
        self.setMinimumSize(900, 600)
        self.resize(1060, 700)
        self.setStyleSheet(MAIN_STYLE)
        self._setup_ui()
        self._load_log(50)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        # 工具栏
        toolbar = QHBoxLayout()
        toolbar.addWidget(QLabel("路径："))
        path_lbl = QLabel(self.path)
        path_lbl.setStyleSheet("color:#89b4fa;font-size:12px;")
        path_lbl.setWordWrap(False)
        toolbar.addWidget(path_lbl, 1)
        toolbar.addWidget(QLabel("加载条数："))
        self.limit_spin = QSpinBox()
        self.limit_spin.setRange(10, 1000)
        self.limit_spin.setValue(50)
        self.limit_spin.setSingleStep(50)
        self.limit_spin.setFixedWidth(80)
        toolbar.addWidget(self.limit_spin)
        refresh_btn = QPushButton("刷新")
        refresh_btn.setFixedSize(60, 28)
        refresh_btn.clicked.connect(
            lambda: self._load_log(self.limit_spin.value()))
        toolbar.addWidget(refresh_btn)
        layout.addLayout(toolbar)

        # 分割器
        splitter = QSplitter(Qt.Orientation.Vertical)
        layout.addWidget(splitter, 1)

        # 日志列表
        self.log_tree = QTreeWidget()
        self.log_tree.setHeaderLabels(["版本", "作者", "日期", "提交说明"])
        self.log_tree.setRootIsDecorated(False)
        self.log_tree.setAlternatingRowColors(True)
        self.log_tree.currentItemChanged.connect(self._on_log_selected)
        hdr = self.log_tree.header()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.log_tree.setColumnWidth(0, 80)
        self.log_tree.setColumnWidth(1, 100)
        self.log_tree.setColumnWidth(2, 160)
        self.log_tree.setStyleSheet("""
            QTreeWidget{background:#181825;alternate-background-color:#1a1a2e;
                border:1px solid #313244;border-radius:6px;outline:none;}
            QTreeWidget::item{height:28px;}
            QTreeWidget::item:selected{background:#313244;}
            QHeaderView::section{background:#111117;color:#a6adc8;
                border:none;border-bottom:1px solid #313244;padding:4px 8px;}
        """)
        splitter.addWidget(self.log_tree)

        # 详情区
        detail_w = QFrame()
        detail_l = QVBoxLayout(detail_w)
        detail_l.setContentsMargins(0, 0, 0, 0)
        detail_l.setSpacing(4)

        # 版本信息行 + 查看 Diff 按钮
        detail_header = QHBoxLayout()
        self.detail_label = QLabel("")
        self.detail_label.setStyleSheet("color:#a6adc8;font-size:12px;padding:4px;")
        detail_header.addWidget(self.detail_label, 1)

        self.diff_btn = QPushButton("⟷  查看本次 Diff")
        self.diff_btn.setFixedHeight(26)
        self.diff_btn.setEnabled(False)
        self.diff_btn.setToolTip("查看本次提交的完整 Diff")
        self.diff_btn.setStyleSheet("""
            QPushButton{
                background:#313244;color:#cdd6f4;border:none;border-radius:4px;
                font-size:12px;padding:0 10px;
            }
            QPushButton:hover{background:#45475a;}
            QPushButton:disabled{color:#585b70;}
        """)
        self.diff_btn.clicked.connect(self._view_revision_diff)
        detail_header.addWidget(self.diff_btn)
        detail_l.addLayout(detail_header)

        self.msg_edit = QTextEdit()
        self.msg_edit.setReadOnly(True)
        self.msg_edit.setMaximumHeight(80)
        self.msg_edit.setStyleSheet(
            "background:#111117;color:#cdd6f4;border:none;padding:4px 8px;"
            "font-size:13px;")
        detail_l.addWidget(self.msg_edit)

        # 变更文件列表提示
        hint_lbl = QLabel("双击文件可查看该文件的 Diff")
        hint_lbl.setStyleSheet("color:#585b70;font-size:11px;padding:0 2px;")
        detail_l.addWidget(hint_lbl)

        self.changed_tree = QTreeWidget()
        self.changed_tree.setHeaderLabels(["操作", "路径"])
        self.changed_tree.setRootIsDecorated(False)
        self.changed_tree.setStyleSheet("""
            QTreeWidget{background:#181825;border:1px solid #313244;border-radius:4px;outline:none;}
            QTreeWidget::item{height:22px;}
            QTreeWidget::item:selected{background:#313244;}
            QTreeWidget::item:hover:!selected{background:#1e1e2e;}
            QHeaderView::section{background:#111117;color:#a6adc8;
                border:none;border-bottom:1px solid #313244;padding:4px 8px;}
        """)
        h = self.changed_tree.header()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.changed_tree.setColumnWidth(0, 60)
        # 双击文件查看 diff
        self.changed_tree.itemDoubleClicked.connect(self._on_file_double_clicked)
        detail_l.addWidget(self.changed_tree)
        splitter.addWidget(detail_w)
        splitter.setSizes([380, 260])

        # 底部状态 + 关闭按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color:#a6adc8;font-size:11px;")
        btn_row.addWidget(self.status_label)
        close_btn = QPushButton("关闭")
        close_btn.setFixedSize(80, 32)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _load_log(self, limit: int):
        self.status_label.setText("正在加载...")
        self.log_tree.clear()
        if self._worker and self._worker.isRunning():
            self._worker.quit()
        self._worker = LogWorker(self.engine, self.path, limit)
        self._worker.finished.connect(self._on_log_loaded)
        self._worker.error.connect(
            lambda e: self.status_label.setText(f"错误: {e}"))
        self._worker.start()

    def _on_log_loaded(self, entries: list[SVNLogEntry]):
        self.log_tree.clear()
        for entry in entries:
            item = QTreeWidgetItem()
            item.setText(0, f"r{entry.revision}")
            item.setForeground(0, QBrush(QColor("#89b4fa")))
            item.setText(1, entry.author)
            item.setForeground(1, QBrush(QColor("#a6e3a1")))
            item.setText(2, format_date(entry.date))
            item.setForeground(2, QBrush(QColor("#a6adc8")))
            msg = entry.message.strip().replace("\n", " ")[:100]
            item.setText(3, msg)
            item.setData(0, Qt.ItemDataRole.UserRole, entry)
            self.log_tree.addTopLevelItem(item)
        self.status_label.setText(f"共 {len(entries)} 条记录")

    def _on_log_selected(self, current, previous):
        if not current:
            return
        entry: SVNLogEntry = current.data(0, Qt.ItemDataRole.UserRole)
        if not entry:
            return
        self._current_entry = entry
        self.detail_label.setText(
            f"版本 r{entry.revision}  |  作者: {entry.author}  |  "
            f"日期: {format_date(entry.date)}"
        )
        self.msg_edit.setPlainText(entry.message)
        self.changed_tree.clear()
        ACTION_MAP = {"M": "修改", "A": "添加", "D": "删除", "R": "替换"}
        for cp in entry.changed_paths:
            item = QTreeWidgetItem()
            action = cp.get("action", "")
            item.setText(0, ACTION_MAP.get(action, action))
            color = {
                "M": "#a6e3a1", "A": "#89dceb",
                "D": "#f38ba8", "R": "#cba6f7",
            }.get(action, "#a6adc8")
            item.setForeground(0, QBrush(QColor(color)))
            item.setText(1, cp.get("path", ""))
            # 保存仓库路径供 diff 使用
            item.setData(0, Qt.ItemDataRole.UserRole, cp.get("path", ""))
            self.changed_tree.addTopLevelItem(item)
        self.diff_btn.setEnabled(True)

    def _view_revision_diff(self):
        """查看整个提交的 diff"""
        if not self._current_entry:
            return
        self._fetch_and_show_diff(
            revision=self._current_entry.revision,
            repo_file_path=None,
            title=f"r{self._current_entry.revision} 完整 Diff"
        )

    def _on_file_double_clicked(self, item: QTreeWidgetItem, column: int):
        """双击变更文件列表中的文件，查看该文件的 diff"""
        if not self._current_entry:
            return
        repo_path = item.data(0, Qt.ItemDataRole.UserRole)
        if not repo_path:
            return
        file_name = repo_path.split("/")[-1]
        self._fetch_and_show_diff(
            revision=self._current_entry.revision,
            repo_file_path=repo_path,
            title=f"r{self._current_entry.revision} — {file_name}"
        )

    def _fetch_and_show_diff(self, revision: str, repo_file_path: str, title: str):
        """后台获取 diff 并弹出查看器"""
        self.status_label.setText("正在获取 Diff...")
        self.diff_btn.setEnabled(False)

        if self._diff_worker and self._diff_worker.isRunning():
            self._diff_worker.quit()

        worker = DiffWorker(self.engine, self.path, revision, repo_file_path)

        def on_finished(diff_text: str):
            self.status_label.setText("")
            self.diff_btn.setEnabled(True)
            if not diff_text.strip():
                diff_text = f"（版本 r{revision} 没有可显示的 Diff 内容）"
            dlg = DiffViewer(
                path=self.path,
                diff_text=diff_text,
                parent=self,
                title=title,
            )
            dlg.exec()

        def on_error(msg: str):
            self.status_label.setText(f"获取 Diff 失败: {msg}")
            self.diff_btn.setEnabled(True)

        worker.finished.connect(on_finished)
        worker.error.connect(on_error)
        self._diff_worker = worker
        worker.start()
