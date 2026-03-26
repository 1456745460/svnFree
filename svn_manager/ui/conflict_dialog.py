"""
冲突解决对话框
支持三路对比视图（mine / base / theirs）和逐块可视化编辑解决
"""
import os
import re
from dataclasses import dataclass
from typing import List, Optional

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QSplitter,
    QLabel, QPushButton, QPlainTextEdit, QWidget,
    QTabWidget, QMessageBox, QFrame, QScrollArea,
    QSizePolicy, QToolBar,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize
from PyQt6.QtGui import (
    QFont, QTextCharFormat, QColor, QSyntaxHighlighter,
    QTextCursor, QTextBlockUserData, QAction,
)

from ..core.svn_engine import SVNEngine
from .theme import MAIN_STYLE
from .file_icons import get_ui_icon


# ── 冲突块数据结构 ────────────────────────────────────────────────────

@dataclass
class ConflictBlock:
    """代表文件中一个冲突块的位置信息"""
    start_line: int    # <<<<<<< 所在行（0-based）
    sep_line: int      # ======= 所在行
    end_line: int      # >>>>>>> 所在行
    mine_lines: List[str]   # <<<< 到 ==== 之间的行
    theirs_lines: List[str] # ==== 到 >>>> 之间的行


def parse_conflict_blocks(text: str) -> List[ConflictBlock]:
    """解析文本中所有冲突块"""
    lines = text.splitlines()
    blocks: List[ConflictBlock] = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("<<<<<<<"):
            start = i
            sep = None
            end = None
            mine: List[str] = []
            theirs: List[str] = []
            j = i + 1
            while j < len(lines):
                if lines[j].startswith("======="):
                    sep = j
                elif lines[j].startswith(">>>>>>>"):
                    end = j
                    break
                elif sep is None:
                    mine.append(lines[j])
                else:
                    theirs.append(lines[j])
                j += 1
            if sep is not None and end is not None:
                blocks.append(ConflictBlock(start, sep, end, mine, theirs))
                i = end + 1
                continue
        i += 1
    return blocks


# ── 冲突块高亮器 ──────────────────────────────────────────────────────

class _ConflictHighlighter(QSyntaxHighlighter):
    """为编辑器中的冲突标记和冲突区域着色"""

    # 颜色常量
    MINE_BG     = QColor("#1a3d1a")
    MINE_FG     = QColor("#a6e3a1")
    THEIRS_BG   = QColor("#1a2a3d")
    THEIRS_FG   = QColor("#89b4fa")
    MARKER_BG   = QColor("#2d2444")
    MARKER_FG   = QColor("#cba6f7")
    MARKER_FONT = 700

    def __init__(self, doc):
        super().__init__(doc)
        self._in_mine = False
        self._in_theirs = False

    def highlightBlock(self, text: str):
        # 判断当前区域
        prev_state = self.previousBlockState()
        # state: 0=normal, 1=mine, 2=theirs
        if prev_state == 1:
            self._in_mine = True
            self._in_theirs = False
        elif prev_state == 2:
            self._in_mine = False
            self._in_theirs = True
        else:
            self._in_mine = False
            self._in_theirs = False

        if text.startswith("<<<<<<<"):
            fmt = QTextCharFormat()
            fmt.setBackground(self.MARKER_BG)
            fmt.setForeground(self.MARKER_FG)
            fmt.setFontWeight(self.MARKER_FONT)
            self.setFormat(0, len(text), fmt)
            self.setCurrentBlockState(1)  # 之后是 mine 区
        elif text.startswith("======="):
            fmt = QTextCharFormat()
            fmt.setBackground(self.MARKER_BG)
            fmt.setForeground(self.MARKER_FG)
            fmt.setFontWeight(self.MARKER_FONT)
            self.setFormat(0, len(text), fmt)
            self.setCurrentBlockState(2)  # 之后是 theirs 区
        elif text.startswith(">>>>>>>"):
            fmt = QTextCharFormat()
            fmt.setBackground(self.MARKER_BG)
            fmt.setForeground(self.MARKER_FG)
            fmt.setFontWeight(self.MARKER_FONT)
            self.setFormat(0, len(text), fmt)
            self.setCurrentBlockState(0)  # 恢复正常
        elif self._in_mine:
            fmt = QTextCharFormat()
            fmt.setBackground(self.MINE_BG)
            fmt.setForeground(self.MINE_FG)
            self.setFormat(0, len(text), fmt)
            self.setCurrentBlockState(1)
        elif self._in_theirs:
            fmt = QTextCharFormat()
            fmt.setBackground(self.THEIRS_BG)
            fmt.setForeground(self.THEIRS_FG)
            self.setFormat(0, len(text), fmt)
            self.setCurrentBlockState(2)
        else:
            self.setCurrentBlockState(0)


# ── 只读代码面板 ──────────────────────────────────────────────────────

def _make_code_view(content: str, label: str,
                    label_color: str = "#cdd6f4") -> QWidget:
    w = QWidget()
    layout = QVBoxLayout(w)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)

    header = QLabel(f"  {label}")
    header.setFixedHeight(28)
    header.setStyleSheet(
        f"background:#181825; color:{label_color}; "
        "font-size:12px; font-weight:600; "
        "border-bottom:1px solid #313244; padding:0 8px;"
    )
    layout.addWidget(header)

    editor = QPlainTextEdit()
    editor.setReadOnly(True)
    editor.setPlainText(content)
    editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
    mono = QFont()
    mono.setStyleHint(QFont.StyleHint.Monospace)
    mono.setFamily("Menlo")
    mono.setPointSize(12)
    editor.setFont(mono)
    editor.setStyleSheet("""
        QPlainTextEdit {
            background:#11111b; color:#cdd6f4;
            border:none; selection-background-color:#45475a;
        }
    """)
    layout.addWidget(editor, 1)
    return w


# ── 冲突导航工具栏 ────────────────────────────────────────────────────

class _ConflictNavBar(QWidget):
    """显示冲突块数量、导航和逐块快速操作按钮"""

    use_mine   = pyqtSignal(int)    # 接受指定块的 mine
    use_theirs = pyqtSignal(int)    # 接受指定块的 theirs
    prev_block = pyqtSignal()
    next_block = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setStyleSheet("background:#181825; border-bottom:1px solid #313244;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 4, 12, 4)
        layout.setSpacing(8)

        self._conflict_label = QLabel("无冲突块")
        self._conflict_label.setStyleSheet("color:#a6adc8; font-size:12px;")
        layout.addWidget(self._conflict_label)

        layout.addStretch()

        # 逐块操作
        self._idx_label = QLabel("")
        self._idx_label.setStyleSheet("color:#f9e2af; font-size:12px; font-weight:600;")
        layout.addWidget(self._idx_label)

        self._btn_prev = self._mk_btn("◀ 上一个", "#a6adc8")
        self._btn_prev.clicked.connect(self.prev_block)
        layout.addWidget(self._btn_prev)

        self._btn_next = self._mk_btn("下一个 ▶", "#a6adc8")
        self._btn_next.clicked.connect(self.next_block)
        layout.addWidget(self._btn_next)

        layout.addWidget(self._sep())

        self._btn_mine   = self._mk_btn("✔ 用本地（mine）",   "#a6e3a1")
        self._btn_theirs = self._mk_btn("✔ 用服务器（theirs）", "#89b4fa")
        layout.addWidget(self._btn_mine)
        layout.addWidget(self._btn_theirs)

        self._cur_block_idx: int = -1
        self._total: int = 0

        self._btn_mine.clicked.connect(
            lambda: self.use_mine.emit(self._cur_block_idx))
        self._btn_theirs.clicked.connect(
            lambda: self.use_theirs.emit(self._cur_block_idx))

        self._set_enabled(False)

    @staticmethod
    def _mk_btn(text: str, color: str) -> QPushButton:
        b = QPushButton(text)
        b.setFixedHeight(28)
        b.setStyleSheet(f"""
            QPushButton {{
                background:#1e1e2e; color:{color};
                border:1px solid {color}44; border-radius:4px;
                padding:0 10px; font-size:11px;
            }}
            QPushButton:hover {{ background:{color}22; border-color:{color}; }}
            QPushButton:pressed {{ background:{color}33; }}
            QPushButton:disabled {{ color:#45475a; border-color:#313244; }}
        """)
        return b

    @staticmethod
    def _sep() -> QFrame:
        f = QFrame()
        f.setFrameShape(QFrame.Shape.VLine)
        f.setStyleSheet("color:#313244;")
        return f

    def update_state(self, total: int, current: int):
        self._total = total
        self._cur_block_idx = current
        if total == 0:
            self._conflict_label.setText("✓ 无冲突块")
            self._conflict_label.setStyleSheet("color:#a6e3a1; font-size:12px;")
            self._idx_label.setText("")
            self._set_enabled(False)
        else:
            self._conflict_label.setText(f"共 {total} 个冲突块")
            self._conflict_label.setStyleSheet("color:#f38ba8; font-size:12px; font-weight:600;")
            if current >= 0:
                self._idx_label.setText(f"当前：第 {current + 1}/{total} 个")
            else:
                self._idx_label.setText("")
            self._set_enabled(total > 0)
            self._btn_prev.setEnabled(current > 0)
            self._btn_next.setEnabled(current < total - 1)

    def _set_enabled(self, enabled: bool):
        for b in (self._btn_prev, self._btn_next,
                  self._btn_mine, self._btn_theirs):
            b.setEnabled(enabled)


# ── 可编辑冲突编辑器 ──────────────────────────────────────────────────

class _ConflictEditor(QWidget):
    """可编辑的冲突文件视图，支持：
    1. 直接编辑文件内容
    2. 逐块导航和一键接受 mine / theirs
    3. 实时更新冲突块统计
    """

    content_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 导航栏
        self.nav = _ConflictNavBar()
        self.nav.use_mine.connect(self._accept_mine_block)
        self.nav.use_theirs.connect(self._accept_theirs_block)
        self.nav.prev_block.connect(self._go_prev)
        self.nav.next_block.connect(self._go_next)
        layout.addWidget(self.nav)

        # 编辑器
        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(False)
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        mono = QFont()
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setFamily("Menlo")
        mono.setPointSize(12)
        self.editor.setFont(mono)
        self.editor.setStyleSheet("""
            QPlainTextEdit {
                background:#11111b; color:#cdd6f4;
                border:none; selection-background-color:#45475a;
            }
        """)
        self._highlighter = _ConflictHighlighter(self.editor.document())
        layout.addWidget(self.editor, 1)

        self._blocks: List[ConflictBlock] = []
        self._cur_idx: int = -1

        self.editor.textChanged.connect(self._on_text_changed)
        self.editor.cursorPositionChanged.connect(self._on_cursor_moved)

    def set_content(self, text: str):
        self.editor.blockSignals(True)
        self.editor.setPlainText(text)
        self.editor.blockSignals(False)
        self._refresh_blocks()

    def get_content(self) -> str:
        return self.editor.toPlainText()

    def _on_text_changed(self):
        self._refresh_blocks()
        self.content_changed.emit()

    def _on_cursor_moved(self):
        if not self._blocks:
            return
        cur_line = self.editor.textCursor().blockNumber()
        for i, blk in enumerate(self._blocks):
            if blk.start_line <= cur_line <= blk.end_line:
                self._cur_idx = i
                self.nav.update_state(len(self._blocks), i)
                return
        # 光标不在冲突块内：保持当前索引不变，只更新导航标签
        self.nav.update_state(len(self._blocks), self._cur_idx)

    def _refresh_blocks(self):
        self._blocks = parse_conflict_blocks(self.editor.toPlainText())
        if not self._blocks:
            self._cur_idx = -1
        elif self._cur_idx >= len(self._blocks):
            self._cur_idx = len(self._blocks) - 1
        self.nav.update_state(len(self._blocks), self._cur_idx)

    # ── 导航 ──────────────────────────────────────────────────────────

    def _go_prev(self):
        if self._cur_idx > 0:
            self._cur_idx -= 1
            self._jump_to_block(self._cur_idx)

    def _go_next(self):
        if self._cur_idx < len(self._blocks) - 1:
            self._cur_idx += 1
            self._jump_to_block(self._cur_idx)
        elif self._cur_idx == -1 and self._blocks:
            self._cur_idx = 0
            self._jump_to_block(0)

    def _jump_to_block(self, idx: int):
        if 0 <= idx < len(self._blocks):
            blk = self._blocks[idx]
            doc = self.editor.document()
            block = doc.findBlockByNumber(blk.start_line)
            cur = QTextCursor(block)
            self.editor.setTextCursor(cur)
            self.editor.centerCursor()
            self.nav.update_state(len(self._blocks), idx)

    # ── 逐块接受 ──────────────────────────────────────────────────────

    def _accept_mine_block(self, idx: int):
        self._replace_block(idx, "mine")

    def _accept_theirs_block(self, idx: int):
        self._replace_block(idx, "theirs")

    def _replace_block(self, idx: int, side: str):
        """将指定冲突块替换为 mine 或 theirs 的内容"""
        if idx < 0 or idx >= len(self._blocks):
            # 若尚未选中块，跳到第一个
            if self._blocks:
                idx = 0
            else:
                return

        blk = self._blocks[idx]
        keep_lines = blk.mine_lines if side == "mine" else blk.theirs_lines

        doc = self.editor.document()
        # 选中从 start_line 到 end_line（含）
        start_block = doc.findBlockByNumber(blk.start_line)
        end_block   = doc.findBlockByNumber(blk.end_line)

        cur = QTextCursor(start_block)
        end_pos = end_block.position() + end_block.length() - 1
        cur.setPosition(end_pos, QTextCursor.MoveMode.KeepAnchor)

        replacement = "\n".join(keep_lines)
        cur.insertText(replacement)

        # 替换后重新解析，跳到下一个冲突块
        self._refresh_blocks()
        if self._blocks:
            next_idx = min(idx, len(self._blocks) - 1)
            self._cur_idx = next_idx
            self._jump_to_block(next_idx)
        else:
            self._cur_idx = -1
            self.nav.update_state(0, -1)


# ── 后台加载线程 ──────────────────────────────────────────────────────

class _LoadWorker(QThread):
    finished = pyqtSignal(dict)
    error    = pyqtSignal(str)

    def __init__(self, engine: SVNEngine, path: str):
        super().__init__()
        self.engine = engine
        self.path = path

    def run(self):
        try:
            versions = self.engine.get_conflict_versions(self.path)
            self.finished.emit(versions)
        except Exception as e:
            self.error.emit(str(e))


# ── 主对话框 ──────────────────────────────────────────────────────────

class ConflictDialog(QDialog):
    """冲突解决对话框

    功能：
    1. 三路面板：mine / base / theirs 只读对比
    2. 可编辑工作文件：直接编辑 + 逐块接受 mine/theirs
    3. 快速解决策略：接受本地 / 接受服务器 / 保存编辑内容并解决
    """

    resolved = pyqtSignal(str)

    def __init__(self, engine: SVNEngine, path: str, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.path = path
        self._versions: dict = {}
        self._worker = None
        self._unsaved = False

        self.setWindowTitle(f"解决冲突 — {os.path.basename(path)}")
        self.setMinimumSize(1100, 700)
        self.resize(1300, 800)
        self.setStyleSheet(MAIN_STYLE)

        self._build_ui()
        self._load_versions()

    # ── UI ────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())

        self.tabs = QTabWidget()
        self.tabs.setStyleSheet("""
            QTabWidget::pane { border:none; background:#1e1e2e; }
            QTabBar::tab {
                background:#181825; color:#a6adc8;
                padding:6px 18px; border:none;
                border-bottom:2px solid transparent;
                font-size:12px;
            }
            QTabBar::tab:selected {
                color:#89b4fa; border-bottom:2px solid #89b4fa;
                background:#1e1e2e;
            }
            QTabBar::tab:hover:!selected { background:#313244; }
        """)

        # Tab1：三路对比（只读）
        self.three_way_tab = QWidget()
        self._build_three_way_tab()
        self.tabs.addTab(self.three_way_tab, "三路对比（mine | base | theirs）")

        # Tab2：可编辑冲突解决器
        self.edit_tab = QWidget()
        self._build_edit_tab()
        self.tabs.addTab(self.edit_tab, "编辑解决（可直接修改 / 逐块选择）")

        root.addWidget(self.tabs, 1)
        root.addWidget(self._build_footer())

    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(48)
        w.setStyleSheet("background:#181825; border-bottom:1px solid #313244;")
        layout = QHBoxLayout(w)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(12)

        icon_lbl = QLabel()
        icon_lbl.setPixmap(get_ui_icon("conflict", "#f38ba8").pixmap(QSize(20, 20)))
        layout.addWidget(icon_lbl)

        title = QLabel(f"冲突文件：{os.path.basename(self.path)}")
        title.setStyleSheet("font-size:14px; font-weight:700; color:#f38ba8;")
        layout.addWidget(title)

        path_lbl = QLabel(self.path)
        path_lbl.setStyleSheet("font-size:11px; color:#585b70;")
        path_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(path_lbl, 1)

        self.loading_label = QLabel("正在加载冲突文件...")
        self.loading_label.setStyleSheet("font-size:12px; color:#a6adc8;")
        layout.addWidget(self.loading_label)

        return w

    def _build_three_way_tab(self):
        layout = QVBoxLayout(self.three_way_tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(2)
        splitter.setStyleSheet("QSplitter::handle { background:#313244; }")

        self._mine_widget   = _make_code_view("加载中...", "本地修改（mine）",    "#a6e3a1")
        self._base_widget   = _make_code_view("加载中...", "公共祖先（base）",    "#a6adc8")
        self._theirs_widget = _make_code_view("加载中...", "服务器版本（theirs）", "#89b4fa")

        splitter.addWidget(self._mine_widget)
        splitter.addWidget(self._base_widget)
        splitter.addWidget(self._theirs_widget)
        splitter.setSizes([430, 430, 430])
        layout.addWidget(splitter)
        self._three_splitter = splitter

    def _build_edit_tab(self):
        """可编辑冲突解决 Tab"""
        layout = QVBoxLayout(self.edit_tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 提示栏
        tip = QLabel(
            "  提示：绿色区域 = 本地（mine），蓝色区域 = 服务器（theirs）。"
            "可直接编辑，或用导航栏逐块选择保留哪一侧。"
            "编辑完成后点击下方「保存并解决」。"
        )
        tip.setFixedHeight(30)
        tip.setStyleSheet(
            "background:#1e1e2e; color:#a6adc8; font-size:11px;"
            "border-bottom:1px solid #313244; padding:0 8px;"
        )
        layout.addWidget(tip)

        self._conflict_editor = _ConflictEditor()
        self._conflict_editor.content_changed.connect(self._on_edit_changed)
        layout.addWidget(self._conflict_editor, 1)

    def _build_footer(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(56)
        w.setStyleSheet("background:#181825; border-top:1px solid #313244;")
        layout = QHBoxLayout(w)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(10)

        hint = QLabel("解决策略：")
        hint.setStyleSheet("font-size:12px; color:#a6adc8;")
        layout.addWidget(hint)

        btn_mine = QPushButton(get_ui_icon("accept_mine", "#a6e3a1"), "  接受全部本地（mine-full）")
        btn_mine.setFixedHeight(36)
        btn_mine.setToolTip("整个文件使用本地版本，忽略服务器修改（--accept=mine-full）")
        btn_mine.setStyleSheet(self._btn_style("#a6e3a1"))
        btn_mine.clicked.connect(self._resolve_mine)
        layout.addWidget(btn_mine)

        btn_theirs = QPushButton(get_ui_icon("accept_theirs", "#89b4fa"), "  接受全部服务器（theirs-full）")
        btn_theirs.setFixedHeight(36)
        btn_theirs.setToolTip("整个文件使用服务器版本，忽略本地修改（--accept=theirs-full）")
        btn_theirs.setStyleSheet(self._btn_style("#89b4fa"))
        btn_theirs.clicked.connect(self._resolve_theirs)
        layout.addWidget(btn_theirs)

        layout.addSpacing(8)
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color:#313244;")
        layout.addWidget(sep)
        layout.addSpacing(8)

        self._btn_save_resolve = QPushButton(
            get_ui_icon("accept_working", "#f9e2af"), "  保存编辑内容并解决")
        self._btn_save_resolve.setFixedHeight(36)
        self._btn_save_resolve.setToolTip(
            "将「编辑解决」Tab 中的当前内容保存到文件，然后执行 svn resolve --accept=working")
        self._btn_save_resolve.setStyleSheet(self._btn_style("#f9e2af"))
        self._btn_save_resolve.clicked.connect(self._resolve_working)
        layout.addWidget(self._btn_save_resolve)

        layout.addStretch()

        btn_cancel = QPushButton("关闭")
        btn_cancel.setFixedHeight(36)
        btn_cancel.setFixedWidth(80)
        btn_cancel.setStyleSheet("""
            QPushButton {
                background:#313244; color:#cdd6f4;
                border:none; border-radius:6px; font-size:13px;
            }
            QPushButton:hover { background:#45475a; }
        """)
        btn_cancel.clicked.connect(self._on_close)
        layout.addWidget(btn_cancel)

        return w

    @staticmethod
    def _btn_style(accent: str) -> str:
        return f"""
            QPushButton {{
                background:#1e1e2e; color:{accent};
                border:1px solid {accent}55; border-radius:6px;
                padding:0 14px; font-size:12px;
            }}
            QPushButton:hover {{
                background:{accent}22; border-color:{accent};
            }}
            QPushButton:pressed {{ background:{accent}33; }}
            QPushButton:disabled {{ color:#45475a; border-color:#313244; }}
        """

    # ── 数据加载 ──────────────────────────────────────────────────────

    def _load_versions(self):
        self._worker = _LoadWorker(self.engine, self.path)
        self._worker.finished.connect(self._on_versions_loaded)
        self._worker.error.connect(self._on_load_error)
        self._worker.start()

    def _on_versions_loaded(self, versions: dict):
        self._versions = versions
        self.loading_label.setText("加载完成")
        self.loading_label.setStyleSheet("font-size:12px; color:#a6e3a1;")

        def _replace_panel(old_widget, content, label, color, filepath=""):
            lbl = f"{label}  [{os.path.basename(filepath)}]" if filepath else label
            new_w = _make_code_view(content, lbl, color)
            splitter = self._three_splitter
            idx = splitter.indexOf(old_widget)
            sizes = splitter.sizes()
            old_widget.setParent(None)
            splitter.insertWidget(idx, new_w)
            splitter.setSizes(sizes)
            return new_w

        if "mine" in versions:
            fp, content = versions["mine"]
            self._mine_widget = _replace_panel(
                self._mine_widget, content, "本地修改（mine）", "#a6e3a1", fp)
        else:
            self._mine_widget = _replace_panel(
                self._mine_widget,
                "（未找到 .mine 文件）\n\n可能是属性冲突或树冲突",
                "本地修改（mine）", "#a6e3a1")

        if "base" in versions:
            fp, content = versions["base"]
            self._base_widget = _replace_panel(
                self._base_widget, content, "公共祖先（base）", "#a6adc8", fp)
        else:
            self._base_widget = _replace_panel(
                self._base_widget, "（未找到 base 版本文件）",
                "公共祖先（base）", "#a6adc8")

        if "theirs" in versions:
            fp, content = versions["theirs"]
            self._theirs_widget = _replace_panel(
                self._theirs_widget, content, "服务器版本（theirs）", "#89b4fa", fp)
        else:
            self._theirs_widget = _replace_panel(
                self._theirs_widget, "（未找到 theirs 版本文件）",
                "服务器版本（theirs）", "#89b4fa")

        # 初始化可编辑器的内容（优先用 working，无则用 mine）
        if "working" in versions:
            _, content = versions["working"]
        elif "mine" in versions:
            _, content = versions["mine"]
        else:
            content = ""
        self._conflict_editor.set_content(content)
        self._unsaved = False

    def _on_load_error(self, msg: str):
        self.loading_label.setText(f"加载失败：{msg}")
        self.loading_label.setStyleSheet("font-size:12px; color:#f38ba8;")

    def _on_edit_changed(self):
        self._unsaved = True

    # ── 解决策略 ──────────────────────────────────────────────────────

    def _do_resolve(self, accept: str, label: str):
        reply = QMessageBox.question(
            self, "确认解决冲突",
            f"确定要以「{label}」策略解决此冲突吗？\n\n"
            f"文件：{self.path}\n\n"
            "此操作将标记文件为已解决状态，无法撤销。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return False

        ok, msg = self.engine.resolve([self.path], accept=accept)
        if ok:
            QMessageBox.information(self, "解决成功",
                                    "冲突已标记为已解决。\n\n请记得提交工作副本以完成本次合并。")
            self.resolved.emit(self.path)
            self.accept()
            return True
        else:
            QMessageBox.critical(self, "解决失败", msg)
            return False

    def _resolve_mine(self):
        self._do_resolve("mine-full", "接受全部本地版本（mine-full）")

    def _resolve_theirs(self):
        self._do_resolve("theirs-full", "接受全部服务器版本（theirs-full）")

    def _resolve_working(self):
        """保存编辑器内容到文件，然后执行 svn resolve --accept=working"""
        content = self._conflict_editor.get_content()

        # 检查是否仍有冲突标记
        remaining = parse_conflict_blocks(content)
        if remaining:
            reply = QMessageBox.warning(
                self, "仍有未解决的冲突块",
                f"编辑内容中仍有 {len(remaining)} 个冲突块未处理\n"
                "（含有 <<<<<<< / ======= / >>>>>>> 标记）。\n\n"
                "是否仍要继续保存并标记为已解决？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        # 写入文件
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                f.write(content)
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"无法写入文件：{e}")
            return

        self._unsaved = False
        self._do_resolve("working", "保存编辑内容（working）")

    def _on_close(self):
        if self._unsaved:
            reply = QMessageBox.question(
                self, "有未保存的编辑",
                "编辑解决 Tab 中有未保存的修改，关闭后将丢失。\n\n确定要关闭吗？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.reject()
