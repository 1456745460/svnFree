"""
工作副本浏览器 - 显示工作副本的文件树和状态（树形结构）
"""
import os
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSplitter,
    QTreeWidget, QTreeWidgetItem, QLabel, QPushButton,
    QHeaderView, QMenu, QAbstractItemView, QFrame,
    QCheckBox, QLineEdit, QToolButton, QApplication,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize, QPoint
from PyQt6.QtGui import QColor, QBrush




from ..core.svn_engine import SVNEngine, SVNStatus, SVNFileStatus, SVNInfo
from .theme import STATUS_COLORS, STATUS_LABELS, MAIN_STYLE, MENU_STYLE
from ..utils.helpers import format_date, shorten_path
from .file_icons import get_file_icon, get_ui_icon, ICON_SIZE


STATUS_ICON = {
    SVNStatus.NORMAL:      "✓",
    SVNStatus.MODIFIED:    "M",
    SVNStatus.ADDED:       "A",
    SVNStatus.DELETED:     "D",
    SVNStatus.CONFLICTED:  "C",
    SVNStatus.UNVERSIONED: "?",
    SVNStatus.MISSING:     "!",
    SVNStatus.REPLACED:    "R",
    SVNStatus.IGNORED:     "I",
    SVNStatus.EXTERNAL:    "X",
    SVNStatus.OBSTRUCTED:  "~",
    SVNStatus.UNKNOWN:     "?",
}


class StatusRefreshWorker(QThread):
    finished = pyqtSignal(list, object)  # status_list, info
    error = pyqtSignal(str)

    def __init__(self, engine: SVNEngine, path: str):
        super().__init__()
        self.engine = engine
        self.path = path

    def run(self):
        try:
            status_list = self.engine.get_status(self.path, verbose=True)
            info = self.engine.get_info(self.path)
            self.finished.emit(status_list, info)
        except Exception as e:
            self.error.emit(str(e))


class WorkingCopyBrowser(QWidget):
    status_message = pyqtSignal(str)
    action_requested = pyqtSignal(str, list)

    def __init__(self, engine: SVNEngine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self._path = ""
        self._all_status: list[SVNFileStatus] = []
        self._worker = None
        self._filter_debounce_timer = QTimer(self)
        self._filter_debounce_timer.setSingleShot(True)
        self._filter_debounce_timer.setInterval(300)
        self._filter_debounce_timer.timeout.connect(self._apply_filter)
        self._setup_ui()

    # ── UI 构建 ───────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_info_bar())

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(self.splitter, 1)

        # 左侧树区域
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_layout.addWidget(self._build_filter_bar())
        self.file_tree = self._build_file_tree()
        left_layout.addWidget(self.file_tree)

        self.stats_label = QLabel("  无数据")
        self.stats_label.setFixedHeight(24)
        self.stats_label.setStyleSheet(
            "color:#a6adc8;font-size:11px;padding:0 8px;"
            "background:#111117;border-top:1px solid #313244;"
        )
        left_layout.addWidget(self.stats_label)
        self.splitter.addWidget(left)

        # 右侧详情面板
        self.splitter.addWidget(self._build_detail_panel())
        self.splitter.setSizes([680, 280])

    def _build_info_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(48)
        bar.setStyleSheet("background:#111117;border-bottom:1px solid #313244;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(12)

        self.path_label = QLabel("选择一个工作副本")
        self.path_label.setStyleSheet("font-size:13px;color:#89b4fa;font-weight:600;")
        layout.addWidget(self.path_label)
        layout.addStretch()

        self.url_label = QLabel("")
        self.url_label.setStyleSheet(
            "font-size:11px;color:#a6adc8;"
            "padding:2px 4px;border-radius:4px;"
        )
        self.url_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.url_label.setToolTip("")
        self.url_label.mousePressEvent = self._on_url_clicked
        layout.addWidget(self.url_label)

        self.rev_label = QLabel("")
        self.rev_label.setStyleSheet(
            "font-size:11px;color:#a6e3a1;background:#1e3a2a;"
            "padding:2px 8px;border-radius:10px;"
        )
        layout.addWidget(self.rev_label)

        refresh_btn = QToolButton()
        refresh_btn.setToolTip("刷新状态")
        refresh_btn.setFixedSize(28, 28)
        refresh_btn.setIcon(get_ui_icon("refresh"))
        refresh_btn.setIconSize(QSize(18, 18))
        refresh_btn.setStyleSheet("""
            QToolButton{background:transparent;border:none;}
            QToolButton:hover{background:#313244;border-radius:4px;}
        """)
        refresh_btn.clicked.connect(self.refresh)
        layout.addWidget(refresh_btn)
        return bar

    def _build_filter_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(38)
        bar.setStyleSheet("background:#181825;border-bottom:1px solid #313244;")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(6)

        self.show_changed_cb = QCheckBox("仅显示变更")
        self.show_changed_cb.setChecked(False)
        self.show_changed_cb.setStyleSheet("color:#a6adc8;font-size:12px;")
        self.show_changed_cb.toggled.connect(self._apply_filter)
        layout.addWidget(self.show_changed_cb)

        self.expand_all_btn = QPushButton("展开全部")
        self.expand_all_btn.setFixedHeight(24)
        self.expand_all_btn.setStyleSheet("""
            QPushButton{background:#313244;color:#cdd6f4;border:none;
                border-radius:4px;padding:0 8px;font-size:11px;}
            QPushButton:hover{background:#45475a;}
        """)
        self.expand_all_btn.clicked.connect(lambda: self.file_tree.expandAll())
        layout.addWidget(self.expand_all_btn)

        self.collapse_all_btn = QPushButton("折叠全部")
        self.collapse_all_btn.setFixedHeight(24)
        self.collapse_all_btn.setStyleSheet("""
            QPushButton{background:#313244;color:#cdd6f4;border:none;
                border-radius:4px;padding:0 8px;font-size:11px;}
            QPushButton:hover{background:#45475a;}
        """)
        self.collapse_all_btn.clicked.connect(lambda: self.file_tree.collapseAll())
        layout.addWidget(self.collapse_all_btn)

        layout.addStretch()

        self.file_search = QLineEdit()
        self.file_search.setPlaceholderText("过滤文件...")
        self.file_search.setFixedWidth(160)
        self.file_search.setStyleSheet("""
            QLineEdit{background:#1e1e2e;color:#cdd6f4;border:1px solid #313244;
                border-radius:4px;padding:3px 8px;font-size:12px;}
        """)
        self.file_search.textChanged.connect(
            lambda _: self._filter_debounce_timer.start()
        )
        layout.addWidget(self.file_search)

        select_all_btn = QPushButton("全选")
        select_all_btn.setFixedHeight(24)
        select_all_btn.setStyleSheet("""
            QPushButton{background:#313244;color:#cdd6f4;border:none;
                border-radius:4px;padding:0 8px;font-size:11px;}
            QPushButton:hover{background:#45475a;}
        """)
        select_all_btn.clicked.connect(self._select_all)
        layout.addWidget(select_all_btn)
        return bar

    def _build_file_tree(self) -> QTreeWidget:
        tree = QTreeWidget()
        tree.setHeaderLabels(["名称", "状态", "版本", "作者"])
        tree.setAlternatingRowColors(False)
        tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        tree.setRootIsDecorated(True)       # 显示折叠/展开箭头
        tree.setAnimated(True)
        tree.setIndentation(20)
        tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tree.customContextMenuRequested.connect(self._file_context_menu)
        tree.currentItemChanged.connect(self._on_file_selected)
        tree.itemClicked.connect(self._on_item_clicked)
        tree.itemDoubleClicked.connect(self._on_file_double_clicked)
        # 展开/折叠时切换文件夹图标
        tree.itemExpanded.connect(self._on_item_expanded)
        tree.itemCollapsed.connect(self._on_item_collapsed)

        header = tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        tree.setColumnWidth(1, 76)
        tree.setColumnWidth(2, 60)
        tree.setColumnWidth(3, 88)

        tree.setStyleSheet("""
            QTreeWidget{
                background:#181825;
                border:none; outline:none; color:#cdd6f4;
                font-size:13px;
            }
            QTreeWidget::item{
                height:26px; padding-left:2px;
            }
            QTreeWidget::item:selected{
                background:#313244; border-radius:4px;
            }
            QTreeWidget::item:hover:!selected{
                background:#252535;
            }
            /* ── 对齐线：竖线连接同级节点 ── */
            QTreeWidget::branch{
                background:#181825;
            }
            QTreeWidget::branch:has-siblings:!adjoins-item {
                border-image: none;
                border-left: 1px solid #3a3a52;
                margin-left: 9px;
                padding-left: 0px;
            }
            QTreeWidget::branch:has-siblings:adjoins-item {
                border-image: none;
                border-left: 1px solid #3a3a52;
                margin-left: 9px;
            }
            QTreeWidget::branch:!has-siblings:adjoins-item {
                border-image: none;
            }
            /* 隐藏系统自带的展开/折叠箭头（使用文字箭头代替）*/
            QTreeWidget::branch:has-children:!has-siblings:closed,
            QTreeWidget::branch:closed:has-children:has-siblings,
            QTreeWidget::branch:open:has-children:!has-siblings,
            QTreeWidget::branch:open:has-children:has-siblings {
                image: none;
                border-image: none;
            }
            QHeaderView::section{
                background:#111117;color:#a6adc8;border:none;
                border-right:1px solid #313244;
                border-bottom:1px solid #313244;
                padding:4px 8px;font-size:12px;
            }
        """)
        return tree

    def _build_detail_panel(self) -> QWidget:
        panel = QFrame()
        panel.setStyleSheet(
            "QFrame{background:#181825;border-left:1px solid #313244;}")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        title = QLabel("文件详情")
        title.setStyleSheet("font-size:13px;font-weight:700;color:#89b4fa;")
        layout.addWidget(title)

        self.detail_filename = QLabel("")
        self.detail_filename.setStyleSheet("font-size:12px;color:#cdd6f4;")
        self.detail_filename.setWordWrap(True)
        layout.addWidget(self.detail_filename)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color:#313244;")
        layout.addWidget(sep)

        self.detail_info = QLabel("")
        self.detail_info.setStyleSheet("font-size:11px;color:#a6adc8;line-height:1.8;")
        self.detail_info.setWordWrap(True)
        self.detail_info.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.detail_info)

        layout.addStretch()

        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(6)
        for label, action, icon_key in [
            ("查看 Diff", "diff",   "diff"),
            ("查看日志",  "log",    "log"),
            ("还原",      "revert", "revert"),
            ("Blame",     "blame",  "blame"),
        ]:
            btn = QPushButton(f"  {label}")
            btn.setFixedHeight(32)
            btn.setIcon(get_ui_icon(icon_key))
            btn.setIconSize(QSize(15, 15))
            btn.setStyleSheet("""
                QPushButton{background:#313244;color:#cdd6f4;border:none;
                    border-radius:6px;font-size:12px;text-align:left;padding-left:8px;}
                QPushButton:hover{background:#45475a;}
            """)
            btn.clicked.connect(lambda checked, a=action: self.action_requested.emit(a, []))
            btn_layout.addWidget(btn)
        layout.addLayout(btn_layout)
        return panel

    # ── 数据加载 ──────────────────────────────────────────────────────

    def load(self, path: str):
        self._path = path
        self.path_label.setText(os.path.basename(path))
        self.url_label.setText("")
        self.rev_label.setText("")
        self.refresh()

    def refresh(self):
        if not self._path:
            return
        self.status_message.emit("正在刷新...")
        if self._worker and self._worker.isRunning():
            self._worker.quit()
        self._worker = StatusRefreshWorker(self.engine, self._path)
        self._worker.finished.connect(self._on_status_loaded)
        self._worker.error.connect(lambda e: self.status_message.emit(f"错误: {e}"))
        self._worker.start()

    def _on_status_loaded(self, status_list: list, info: SVNInfo):
        self._all_status = status_list
        if info:
            self.url_label.setText(shorten_path(info.url, 60))
            self.url_label.setToolTip(info.url or "")  # 完整 URL 存入 toolTip
            self.rev_label.setText(f"r{info.revision}")
            self.path_label.setText(
                f"{os.path.basename(self._path)}  ({info.last_changed_author})")
        self._apply_filter()
        self.status_message.emit(
            f"已加载 {len(status_list)} 个条目  •  {self._path}")

    def _apply_filter(self):
        show_changed_only = self.show_changed_cb.isChecked()
        search_text = self.file_search.text().strip().lower()

        filtered = self._all_status
        if show_changed_only:
            filtered = [s for s in filtered
                        if s.status not in (SVNStatus.NORMAL, SVNStatus.IGNORED)]
        if search_text:
            filtered = [s for s in filtered
                        if search_text in s.path.lower()]

        self._populate_tree(filtered)

        modified   = sum(1 for s in self._all_status if s.status == SVNStatus.MODIFIED)
        added      = sum(1 for s in self._all_status if s.status == SVNStatus.ADDED)
        deleted    = sum(1 for s in self._all_status if s.status == SVNStatus.DELETED)
        conflicted = sum(1 for s in self._all_status if s.status == SVNStatus.CONFLICTED)
        self.stats_label.setText(
            f"  显示 {len(filtered)} 项  •  "
            f"修改 {modified}  添加 {added}  删除 {deleted}  冲突 {conflicted}"
        )

    # ── 树形填充（核心逻辑）──────────────────────────────────────────

    def _populate_tree(self, status_list: list[SVNFileStatus]):
        """
        将平铺的路径列表构建为真正的层级树。
        算法：以 base_path 为根，按相对路径逐级插入。
        """
        self.file_tree.setUpdatesEnabled(False)
        self.file_tree.clear()

        base = self._path
        # dir_items: 相对目录路径 -> QTreeWidgetItem
        dir_items: dict[str, QTreeWidgetItem] = {}

        # 按路径长度排序，确保父目录先于子文件处理
        sorted_list = sorted(status_list, key=lambda s: s.path)

        for fs in sorted_list:
            rel = os.path.relpath(fs.path, base) if base else fs.path
            if rel == ".":
                # 根目录本身，跳过（已由 path_label 显示）
                continue

            parts = rel.replace("\\", "/").split("/")
            parent_item = self._ensure_dir_path(parts[:-1], dir_items, base)
            item = self._make_item(fs, parts[-1])

            if parent_item is None:
                self.file_tree.addTopLevelItem(item)
            else:
                parent_item.addChild(item)

            # 如果是目录，注册到 dir_items
            if fs.is_dir:
                dir_items[rel] = item

        # 搜索/变更模式下展开全部；否则默认折叠全部
        if self.show_changed_cb.isChecked() or self.file_search.text():
            self.file_tree.expandAll()
        else:
            self.file_tree.collapseAll()

        self.file_tree.setUpdatesEnabled(True)

    def _ensure_dir_path(self, parts: list[str],
                         dir_items: dict[str, QTreeWidgetItem],
                         base: str) -> "QTreeWidgetItem | None":
        """
        确保 parts 描述的目录层级都存在于树中，不存在则创建占位节点。
        返回最深一级目录的 QTreeWidgetItem，parts 为空时返回 None（根级）。
        """
        if not parts:
            return None

        for depth in range(1, len(parts) + 1):
            rel_dir = "/".join(parts[:depth])
            if rel_dir in dir_items:
                continue
            # 创建缺失的目录节点（可能是 svn status 没单独列出的中间目录）
            dir_path = os.path.join(base, rel_dir.replace("/", os.sep))
            placeholder = QTreeWidgetItem()
            placeholder.setText(0, parts[depth - 1])
            placeholder.setIcon(0, get_file_icon("", is_dir=True, expanded=False))
            placeholder.setForeground(0, QBrush(QColor("#89b4fa")))
            placeholder.setData(0, Qt.ItemDataRole.UserRole, dir_path)
            placeholder.setData(0, Qt.ItemDataRole.UserRole + 1, None)
            placeholder.setToolTip(0, dir_path)

            parent_rel = "/".join(parts[:depth - 1])
            parent_item = dir_items.get(parent_rel)
            if parent_item is None:
                self.file_tree.addTopLevelItem(placeholder)
            else:
                parent_item.addChild(placeholder)

            dir_items[rel_dir] = placeholder

        return dir_items["/".join(parts)]

    def _make_item(self, fs: SVNFileStatus, name: str) -> QTreeWidgetItem:
        """创建单个文件/目录的树节点"""
        item = QTreeWidgetItem()

        status_word  = fs.status.value
        status_label = STATUS_LABELS.get(status_word, status_word)
        color_hex    = STATUS_COLORS.get(status_word, "#cdd6f4")
        color        = QColor(color_hex)
        is_normal    = fs.status in (SVNStatus.NORMAL,)

        # 列0：图标（qtawesome）+ 文件名
        ext_or_name = (
            os.path.splitext(name)[1].lower()   # 有后缀时用后缀
            or name.lower()                      # 无后缀时用文件名（如 Makefile）
        )
        icon = get_file_icon(ext_or_name, is_dir=fs.is_dir, expanded=False)
        item.setIcon(0, icon)
        item.setData(0, Qt.ItemDataRole.DecorationRole + 10, bool(fs.is_dir))  # 记录是否目录

        display_name = name
        # 属性有变更时在名称后面加标记
        prop_word = fs.prop_status.value
        if prop_word not in ("normal", "none"):
            display_name = name + "  [P]"
            item.setForeground(0, QBrush(QColor("#f9e2af")))
        else:
            # normal 文件用柔和色，变更文件用醒目色
            name_color = QColor("#cdd6f4") if is_normal else color
            item.setForeground(0, QBrush(name_color))

        item.setText(0, display_name)

        # 目录有变更时加粗字体突出
        if not is_normal and fs.is_dir:
            from PyQt6.QtGui import QFont
            f = item.font(0)
            f.setBold(True)
            item.setFont(0, f)

        # 列1：中文状态标签（normal 用低调灰色，变更用醒目色）
        item.setText(1, status_label)
        item.setForeground(1, QBrush(QColor("#585b70") if is_normal else color))
        item.setTextAlignment(1, Qt.AlignmentFlag.AlignCenter)

        # 列2：版本
        if fs.revision:
            item.setText(2, fs.revision)
            item.setForeground(2, QBrush(QColor("#6c7086")))
            item.setTextAlignment(2, Qt.AlignmentFlag.AlignCenter)

        # 列3：作者
        if fs.author:
            item.setText(3, fs.author)
            item.setForeground(3, QBrush(QColor("#a6adc8")))

        item.setToolTip(0, fs.path)
        item.setData(0, Qt.ItemDataRole.UserRole, fs.path)
        item.setData(0, Qt.ItemDataRole.UserRole + 1, fs)
        return item

    # ── 文件夹图标切换 ────────────────────────────────────────────────

    @staticmethod
    def _update_dir_icon(item: QTreeWidgetItem, expanded: bool):
        """展开/折叠时切换目录图标"""
        # 通过存储的 is_dir 标记或 UserRole+1 为 None（占位目录）判断
        fs = item.data(0, Qt.ItemDataRole.UserRole + 1)
        is_dir_item = (fs is None) or (hasattr(fs, "is_dir") and fs.is_dir)
        if is_dir_item:
            item.setIcon(0, get_file_icon("", is_dir=True, expanded=expanded))

    def _on_item_expanded(self, item: QTreeWidgetItem):
        self._update_dir_icon(item, expanded=True)

    def _on_item_collapsed(self, item: QTreeWidgetItem):
        self._update_dir_icon(item, expanded=False)

    # ── 事件处理 ──────────────────────────────────────────────────────

    def _is_dir_item(self, item: QTreeWidgetItem) -> bool:
        """判断是否为目录节点"""
        fs = item.data(0, Qt.ItemDataRole.UserRole + 1)
        if fs is None:
            # 占位目录节点
            return True
        return hasattr(fs, "is_dir") and fs.is_dir

    def _on_item_clicked(self, item: QTreeWidgetItem, column: int):
        """单击目录节点时切换展开/折叠"""
        if self._is_dir_item(item):
            if item.isExpanded():
                self.file_tree.collapseItem(item)
            else:
                self.file_tree.expandItem(item)

    def _on_file_selected(self, current, previous):
        if not current:
            self.detail_filename.setText("")
            self.detail_info.setText("")
            return
        fs: SVNFileStatus = current.data(0, Qt.ItemDataRole.UserRole + 1)
        path = current.data(0, Qt.ItemDataRole.UserRole)
        if not path:
            return

        self.detail_filename.setText(os.path.basename(path))

        if fs is None:
            # 占位目录节点
            self.detail_info.setText(
                f'<span style="color:#89b4fa">&#x1F4C1; 目录</span><br>'
                f'<span style="color:#6c7086;font-size:11px">{path}</span>'
            )
            return

        status_word  = fs.status.value
        color        = STATUS_COLORS.get(status_word, "#cdd6f4")
        status_label = STATUS_LABELS.get(status_word, status_word)
        lines = [
            f'<span style="color:{color}">● {status_label}</span>',
            "<b>完整路径：</b>",
            f'<span style="color:#a6adc8;font-size:11px">{path}</span>',
        ]
        if fs.revision:
            lines.append(f"<b>版本：</b> r{fs.revision}")
        if fs.author:
            lines.append(f"<b>作者：</b> {fs.author}")
        if fs.locked:
            lines.append('<span style="color:#f9e2af">&#x1F512; 已锁定</span>')
        if fs.switched:
            lines.append('<span style="color:#cba6f7">&#x21C4; 已切换</span>')
        self.detail_info.setText("<br>".join(lines))

    def _on_file_double_clicked(self, item, column):
        # 目录节点双击由 Qt 默认处理展开/折叠，不触发 diff
        if self._is_dir_item(item):
            return
        path = item.data(0, Qt.ItemDataRole.UserRole)
        if path and os.path.isfile(path):
            self.action_requested.emit("diff", [path])

    # ── 右键菜单 ──────────────────────────────────────────────────────

    def _file_context_menu(self, pos):
        items = self.file_tree.selectedItems()
        if not items:
            return

        paths = [it.data(0, Qt.ItemDataRole.UserRole) for it in items
                 if it.data(0, Qt.ItemDataRole.UserRole)]
        fs_list: list[SVNFileStatus] = [
            it.data(0, Qt.ItemDataRole.UserRole + 1) for it in items]

        if not paths:
            return

        menu = QMenu(self)
        menu.setStyleSheet(MENU_STYLE)

        if len(items) == 1:
            act = menu.addAction(get_ui_icon("diff"),  "查看 Diff")
            act.triggered.connect(lambda: self.action_requested.emit("diff", paths))
            act = menu.addAction(get_ui_icon("log"),   "查看日志...")
            act.triggered.connect(lambda: self.action_requested.emit("log", paths))
            act = menu.addAction(get_ui_icon("blame"), "Blame（逐行）")
            act.triggered.connect(lambda: self.action_requested.emit("blame", paths))
            menu.addSeparator()

        # 冲突文件专属菜单
        has_conflict = any(
            fs and fs.status == SVNStatus.CONFLICTED for fs in fs_list)
        if has_conflict:
            act = menu.addAction(get_ui_icon("conflict", "#f38ba8"), "解决冲突...")
            act.triggered.connect(lambda: self.action_requested.emit("resolve_conflict", paths))
            menu.addSeparator()

        act = menu.addAction(get_ui_icon("commit"),  "提交...")
        act.triggered.connect(lambda: self.action_requested.emit("commit", paths))
        act = menu.addAction(get_ui_icon("update"),  "更新")
        act.triggered.connect(lambda: self.action_requested.emit("update", paths))
        act = menu.addAction(get_ui_icon("revert"),  "还原...")
        act.triggered.connect(lambda: self.action_requested.emit("revert", paths))
        menu.addSeparator()

        has_unversioned = any(
            fs and fs.status == SVNStatus.UNVERSIONED for fs in fs_list)
        if has_unversioned:
            act = menu.addAction(get_ui_icon("add"), "添加到版本控制")
            act.triggered.connect(lambda: self.action_requested.emit("add", paths))

        act = menu.addAction(get_ui_icon("delete"), "删除")
        act.triggered.connect(lambda: self.action_requested.emit("delete", paths))
        menu.addSeparator()

        act = menu.addAction(get_ui_icon("lock"), "锁定")
        act.triggered.connect(lambda: self.action_requested.emit("lock", paths))

        has_locked = any(fs and fs.locked for fs in fs_list)
        if has_locked:
            act = menu.addAction(get_ui_icon("unlock"), "解锁")
            act.triggered.connect(lambda: self._do_unlock(paths))

        menu.addSeparator()
        act = menu.addAction(get_ui_icon("properties"), "属性...")
        act.triggered.connect(lambda: self.action_requested.emit("properties", paths))
        menu.addSeparator()

        cleanup_path = paths[0] if len(paths) == 1 else self._path
        if cleanup_path and os.path.isdir(cleanup_path):
            act = menu.addAction(get_ui_icon("cleanup"), "清理工作副本 (cleanup)")
            act.triggered.connect(
                lambda p=cleanup_path: self.action_requested.emit("cleanup", [p]))
            menu.addSeparator()

        act = menu.addAction(get_ui_icon("open_finder"), "在 Finder 中显示")
        act.triggered.connect(lambda: self._reveal_in_finder(paths[0]))

        menu.exec(self.file_tree.mapToGlobal(pos))

    def _do_unlock(self, paths: list):
        ok, msg = self.engine.unlock(paths)
        self.status_message.emit("解锁成功" if ok else f"解锁失败: {msg}")
        self.refresh()

    def _reveal_in_finder(self, path: str):
        if not path:
            return
        import subprocess
        if os.path.isfile(path):
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["open", path])

    # ── 公共接口 ──────────────────────────────────────────────────────

    def _on_url_clicked(self, event):
        """点击 SVN 地址标签时复制到剪贴板并弹出提示"""
        url = self.url_label.toolTip()
        if not url:
            return
        QApplication.clipboard().setText(url)
        self.status_message.emit(f"已复制：{url}")
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(self, "已复制", f"SVN 地址已复制到剪贴板：\n{url}")

    def get_selected_paths(self) -> list[str]:
        return [
            it.data(0, Qt.ItemDataRole.UserRole)
            for it in self.file_tree.selectedItems()
            if it.data(0, Qt.ItemDataRole.UserRole)
        ]

    def _select_all(self):
        self.file_tree.selectAll()
