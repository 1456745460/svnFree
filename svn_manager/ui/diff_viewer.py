"""
Diff 查看器 - 语法高亮差异显示
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QPlainTextEdit, QSplitter, QFrame,
    QComboBox, QToolButton,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import (
    QColor, QTextCharFormat, QSyntaxHighlighter,
    QFont, QTextDocument,
)

from ..core.svn_engine import SVNEngine
from .theme import MAIN_STYLE


class DiffHighlighter(QSyntaxHighlighter):
    """Diff 语法高亮"""

    def __init__(self, document: QTextDocument):
        super().__init__(document)
        self._added_fmt = QTextCharFormat()
        self._added_fmt.setBackground(QColor("#1a3a2a"))
        self._added_fmt.setForeground(QColor("#a6e3a1"))

        self._removed_fmt = QTextCharFormat()
        self._removed_fmt.setBackground(QColor("#3a1a1a"))
        self._removed_fmt.setForeground(QColor("#f38ba8"))

        self._header_fmt = QTextCharFormat()
        self._header_fmt.setForeground(QColor("#89b4fa"))
        self._header_fmt.setFontWeight(QFont.Weight.Bold)

        self._hunk_fmt = QTextCharFormat()
        self._hunk_fmt.setForeground(QColor("#cba6f7"))
        self._hunk_fmt.setFontWeight(QFont.Weight.Bold)

        self._meta_fmt = QTextCharFormat()
        self._meta_fmt.setForeground(QColor("#a6adc8"))

    def highlightBlock(self, text: str):
        if text.startswith("+++ ") or text.startswith("--- "):
            self.setFormat(0, len(text), self._header_fmt)
        elif text.startswith("@@"):
            self.setFormat(0, len(text), self._hunk_fmt)
        elif text.startswith("+"):
            self.setFormat(0, len(text), self._added_fmt)
        elif text.startswith("-"):
            self.setFormat(0, len(text), self._removed_fmt)
        elif text.startswith("Index:") or text.startswith("====="):
            self.setFormat(0, len(text), self._meta_fmt)


class DiffFetchWorker(QThread):
    finished = pyqtSignal(str)

    def __init__(self, engine: SVNEngine, path: str,
                 rev1: str = None, rev2: str = None):
        super().__init__()
        self.engine = engine
        self.path = path
        self.rev1 = rev1
        self.rev2 = rev2

    def run(self):
        diff = self.engine.get_diff(self.path, self.rev1, self.rev2)
        self.finished.emit(diff)


class DiffViewer(QDialog):
    def __init__(self, path: str, diff_text: str = "",
                 parent=None, title: str = "Diff 查看器"):
        super().__init__(parent)
        self.path = path
        self.setWindowTitle(f"{title} — {path}")
        self.setMinimumSize(900, 600)
        self.resize(1100, 700)
        self.setStyleSheet(MAIN_STYLE)
        self._setup_ui()
        if diff_text:
            self._set_diff(diff_text)

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 工具栏
        toolbar = QFrame()
        toolbar.setFixedHeight(44)
        toolbar.setStyleSheet(
            "background:#111117;border-bottom:1px solid #313244;")
        tb_layout = QHBoxLayout(toolbar)
        tb_layout.setContentsMargins(12, 0, 12, 0)
        tb_layout.setSpacing(8)

        self.path_label = QLabel(self.path)
        self.path_label.setStyleSheet("font-size:12px;color:#a6adc8;")
        self.path_label.setWordWrap(False)
        tb_layout.addWidget(self.path_label, 1)

        self.stats_label = QLabel("")
        self.stats_label.setStyleSheet("font-size:11px;color:#a6adc8;")
        tb_layout.addWidget(self.stats_label)

        close_btn = QPushButton("关闭")
        close_btn.setFixedSize(64, 28)
        close_btn.clicked.connect(self.accept)
        tb_layout.addWidget(close_btn)
        layout.addWidget(toolbar)

        # Diff 文本区
        self.text_view = QPlainTextEdit()
        self.text_view.setObjectName("diffView")
        self.text_view.setReadOnly(True)
        self.text_view.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.text_view.setStyleSheet("""
            QPlainTextEdit{
                font-family:'SF Mono','JetBrains Mono',Menlo,monospace;
                font-size:12px; background:#181825; color:#cdd6f4;
                border:none; padding:8px;
            }
        """)
        self.highlighter = DiffHighlighter(self.text_view.document())
        layout.addWidget(self.text_view)

    def _set_diff(self, diff_text: str):
        self.text_view.setPlainText(diff_text)
        # 统计
        lines = diff_text.splitlines()
        added = sum(1 for l in lines if l.startswith("+") and not l.startswith("+++"))
        removed = sum(1 for l in lines if l.startswith("-") and not l.startswith("---"))
        self.stats_label.setText(
            f'<span style="color:#a6e3a1">+{added}</span>  '
            f'<span style="color:#f38ba8">-{removed}</span>'
        )
        self.stats_label.setTextFormat(Qt.TextFormat.RichText)
