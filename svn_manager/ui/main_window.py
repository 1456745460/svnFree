"""
主窗口 - SVN 管理器主界面
"""
import os
import sys
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTreeWidget, QTreeWidgetItem, QLabel,
    QToolBar, QStatusBar, QMessageBox, QFileDialog,
    QInputDialog, QMenu, QApplication, QFrame,
    QSizePolicy, QPushButton, QLineEdit, QScrollArea,
    QStackedWidget,
)
from PyQt6.QtCore import (
    Qt, QThread, pyqtSignal, QTimer, QSize, QPoint
)

# 防抖延迟（毫秒）
_DEBOUNCE_MS = 300
from PyQt6.QtGui import (
    QIcon, QAction, QFont, QColor, QPixmap,
    QPainter, QBrush, QPen, QKeySequence, QFontMetrics
)

from ..core.svn_engine import SVNEngine, SVNStatus
from ..core.repo_manager import RepoManager, Repository
from ..core.file_watcher import FileWatcher
from .theme import MAIN_STYLE, STATUS_COLORS, STATUS_LABELS, MENU_STYLE
from .commit_dialog import CommitDialog
from .log_dialog import LogDialog
from .diff_viewer import DiffViewer
from .checkout_dialog import CheckoutDialog
from .update_dialog import UpdateDialog
from .properties_dialog import PropertiesDialog
from .working_copy_browser import WorkingCopyBrowser
from .file_icons import get_ui_icon, get_file_icon
from .auth_dialog import AuthDialog
from .conflict_dialog import ConflictDialog


class StatusWorker(QThread):
    """后台刷新状态"""
    finished = pyqtSignal(str, list)   # path, status_list
    error = pyqtSignal(str, str)

    def __init__(self, engine: SVNEngine, path: str):
        super().__init__()
        self.engine = engine
        self.path = path

    def run(self):
        try:
            status_list = self.engine.get_status(self.path)
            self.finished.emit(self.path, status_list)
        except Exception as e:
            self.error.emit(self.path, str(e))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.engine = SVNEngine()
        self.repo_manager = RepoManager()
        self.file_watcher = FileWatcher(self)
        self._workers: list[QThread] = []
        self._current_path: str = ""
        self._status_cache: dict = {}
        self._search_debounce_timer = QTimer(self)
        self._search_debounce_timer.setSingleShot(True)
        self._search_debounce_timer.setInterval(_DEBOUNCE_MS)
        self._search_debounce_timer.timeout.connect(self._do_filter_repos)

        self._setup_ui()
        self._setup_menu()
        self._setup_toolbar()
        self._setup_statusbar()
        self._connect_signals()
        self._load_repos()
        self._apply_style()

    # ── UI 搭建 ──────────────────────────────────────────────────────

    def _setup_ui(self):
        self.setWindowTitle("SVNFree — SVN 管理器")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 主分割器
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(self.splitter)

        # 左侧边栏
        self.sidebar = self._build_sidebar()
        self.sidebar.setObjectName("sidebar")
        self.sidebar.setFixedWidth(240)
        self.splitter.addWidget(self.sidebar)

        # 右侧内容区（堆叠页）
        self.stack = QStackedWidget()
        self.stack.setObjectName("contentArea")
        self.splitter.addWidget(self.stack)
        self.splitter.setStretchFactor(1, 1)

        # 欢迎页
        self.welcome_page = self._build_welcome_page()
        self.stack.addWidget(self.welcome_page)

        # 工作副本浏览页
        self.wc_browser = WorkingCopyBrowser(self.engine, self)
        self.stack.addWidget(self.wc_browser)

        self.stack.setCurrentWidget(self.welcome_page)

    def _build_sidebar(self) -> QWidget:
        w = QWidget()
        w.setObjectName("sidebar")
        layout = QVBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题区
        title_bar = QWidget()
        title_bar.setFixedHeight(52)
        title_bar.setStyleSheet("background:#111117; border-bottom:1px solid #313244;")
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(12, 8, 12, 8)

        title_lbl = QLabel("SVNFree")
        title_lbl.setStyleSheet("font-size:16px;font-weight:700;color:#89b4fa;")
        tb_layout.addWidget(title_lbl)
        tb_layout.addStretch()

        add_btn = QPushButton()
        add_btn.setObjectName("addBtn")
        add_btn.setFixedSize(24, 24)
        add_btn.setIcon(get_ui_icon("add_repo", "#cdd6f4"))
        add_btn.setIconSize(QSize(14, 14))
        add_btn.setStyleSheet("""
            QPushButton#addBtn{
                background:#313244;border:none;border-radius:12px;
                padding:0px;margin:0px;
            }
            QPushButton#addBtn:hover{background:#45475a;}
        """)
        add_btn.setToolTip("添加工作副本")
        add_btn.clicked.connect(self._add_working_copy)
        tb_layout.addWidget(add_btn)
        layout.addWidget(title_bar)

        # 搜索框
        search = QLineEdit()
        search.setPlaceholderText("搜索工作副本...")
        search.setStyleSheet("""
            QLineEdit{
                background:#181825; color:#cdd6f4;
                border:none; border-bottom:1px solid #313244;
                padding:8px 12px; font-size:12px;
            }
            QLineEdit:focus{ border-bottom:1px solid #89b4fa; }
        """)
        search.textChanged.connect(self._on_search_input_changed)
        self.search_input = search
        layout.addWidget(search)

        # 工作副本列表
        self.repo_list = QTreeWidget()
        self.repo_list.setHeaderHidden(True)
        self.repo_list.setRootIsDecorated(False)
        self.repo_list.setSelectionMode(
            QTreeWidget.SelectionMode.SingleSelection)
        self.repo_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.repo_list.customContextMenuRequested.connect(
            self._repo_context_menu)
        self.repo_list.currentItemChanged.connect(
            self._on_repo_selected)
        self.repo_list.setStyleSheet("""
            QTreeWidget{background:#181825;border:none;outline:none;}
            QTreeWidget::item{height:44px;padding:0 8px;border-bottom:1px solid #1e1e2e;}
            QTreeWidget::item:selected{background:#313244;}
            QTreeWidget::item:hover:!selected{background:#1e1e2e;}
        """)
        layout.addWidget(self.repo_list, 1)

        # 底部按钮区
        bottom = QWidget()
        bottom.setFixedHeight(44)
        bottom.setStyleSheet("background:#111117; border-top:1px solid #313244;")
        bot_layout = QHBoxLayout(bottom)
        bot_layout.setContentsMargins(8, 4, 8, 4)
        bot_layout.setSpacing(4)

        for icon_key, tooltip, slot in [
            ("add_repo",   "添加工作副本", self._add_working_copy),
            ("checkout",   "检出仓库",     self._checkout),
            ("preferences","偏好设置",     self._show_preferences),
        ]:
            btn = QPushButton()
            btn.setFixedSize(32, 32)
            btn.setIcon(get_ui_icon(icon_key))
            btn.setIconSize(QSize(18, 18))
            btn.setToolTip(tooltip)
            btn.setStyleSheet("""
                QPushButton{background:transparent;border:none;border-radius:4px;
                    padding:0px;margin:0px;}
                QPushButton:hover{background:#313244;}
            """)
            btn.clicked.connect(slot)
            bot_layout.addWidget(btn)
        bot_layout.addStretch()
        layout.addWidget(bottom)

        return w

    def _build_welcome_page(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)

        # 大图标用 qtawesome 渲染到 QLabel
        icon_lbl = QLabel()
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _pix = get_ui_icon("welcome", "#89b4fa").pixmap(QSize(72, 72))
        icon_lbl.setPixmap(_pix)
        layout.addWidget(icon_lbl)

        title = QLabel("欢迎使用 SVNFree")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-size:22px;font-weight:700;color:#89b4fa;")
        layout.addWidget(title)

        sub = QLabel("点击左侧 + 添加工作副本，或检出一个仓库开始工作")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sub.setStyleSheet("font-size:13px;color:#a6adc8;")
        layout.addWidget(sub)

        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(12)
        btn_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        add_btn = QPushButton("  添加工作副本")
        add_btn.setObjectName("primaryBtn")
        add_btn.setFixedHeight(40)
        add_btn.setIcon(get_ui_icon("add_repo", "#1e1e2e"))
        add_btn.setIconSize(QSize(16, 16))
        add_btn.clicked.connect(self._add_working_copy)
        btn_layout.addWidget(add_btn)

        co_btn = QPushButton("  检出仓库")
        co_btn.setFixedHeight(40)
        co_btn.setIcon(get_ui_icon("checkout"))
        co_btn.setIconSize(QSize(16, 16))
        co_btn.clicked.connect(self._checkout)
        btn_layout.addWidget(co_btn)

        layout.addLayout(btn_layout)
        return w

    def _setup_menu(self):
        mb = self.menuBar()

        # ── 仓库 ──
        repo_menu = mb.addMenu("仓库(&R)")
        self._act(repo_menu, "添加工作副本...", self._add_working_copy, "Ctrl+O")
        self._act(repo_menu, "检出仓库...", self._checkout, "Ctrl+Shift+O")
        repo_menu.addSeparator()
        self._act(repo_menu, "移除工作副本", self._remove_working_copy)
        repo_menu.addSeparator()
        self._act(repo_menu, "退出", self.close, "Ctrl+Q")

        # ── 工作副本 ──
        wc_menu = mb.addMenu("工作副本(&W)")
        self._act(wc_menu, "更新", self._do_update, "Ctrl+U")
        self._act(wc_menu, "提交...", self._do_commit, "Ctrl+Return")
        wc_menu.addSeparator()
        self._act(wc_menu, "还原...", self._do_revert, "Ctrl+Z")
        wc_menu.addSeparator()
        self._act(wc_menu, "解决冲突...", self._do_resolve_conflict, "Ctrl+Shift+R")
        wc_menu.addSeparator()
        self._act(wc_menu, "添加文件", self._do_add)
        self._act(wc_menu, "删除文件", self._do_delete)
        wc_menu.addSeparator()
        self._act(wc_menu, "清理", self._do_cleanup)
        self._act(wc_menu, "切换分支...", self._do_switch)

        # ── 查看 ──
        view_menu = mb.addMenu("查看(&V)")
        self._act(view_menu, "刷新状态", self._refresh_current, "F5")
        self._act(view_menu, "清理工作副本 (Cleanup)", self._do_cleanup, "Ctrl+Shift+C")
        view_menu.addSeparator()
        self._act(view_menu, "查看日志...", self._do_log, "Ctrl+L")
        self._act(view_menu, "查看 Diff...", self._do_diff, "Ctrl+D")
        self._act(view_menu, "查看属性...", self._do_properties)
        view_menu.addSeparator()
        self._act(view_menu, "Blame（逐行信息）", self._do_blame)

        # ── 帮助 ──
        help_menu = mb.addMenu("帮助(&H)")
        self._act(help_menu, "关于 SVNFree", self._show_about)

    def _act(self, menu, title, slot, shortcut=None):
        action = QAction(title, self)
        if shortcut:
            action.setShortcut(QKeySequence(shortcut))
        action.triggered.connect(slot)
        menu.addAction(action)
        return action

    def _setup_toolbar(self):
        tb = self.addToolBar("主工具栏")
        tb.setMovable(False)
        tb.setIconSize(QSize(18, 18))
        tb.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        # (icon_key, label, tooltip, slot)
        tools = [
            ("update",   "更新",  "更新工作副本到最新版本",  self._do_update),
            ("commit",   "提交",  "提交修改到服务器",        self._do_commit),
            ("revert",   "还原",  "放弃本地修改",             self._do_revert),
            (None, None, None, None),
            ("log",      "日志",  "查看提交历史",             self._do_log),
            ("diff",     "Diff",  "查看文件差异",             self._do_diff),
            (None, None, None, None),
            ("add",      "添加",  "将文件加入版本控制",       self._do_add),
            ("lock",     "锁定",  "锁定文件",                 self._do_lock),
            (None, None, None, None),
            ("refresh",  "刷新",  "刷新当前状态",             self._refresh_current),
            ("cleanup",  "清理",  "清理工作副本 (Cleanup)",   self._do_cleanup),
        ]

        for icon_key, label, tip, slot in tools:
            if icon_key is None:
                tb.addSeparator()
                continue
            act = QAction(get_ui_icon(icon_key), label, self)
            if tip:
                act.setToolTip(tip)
            if slot:
                act.triggered.connect(slot)
            tb.addAction(act)

    def _setup_statusbar(self):
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_label = QLabel("就绪")
        self.status_bar.addWidget(self.status_label)

    def _connect_signals(self):
        self.file_watcher.changed.connect(self._on_file_changed)
        self.wc_browser.status_message.connect(self._set_status)
        self.wc_browser.action_requested.connect(self._handle_browser_action)

    def _apply_style(self):
        self.setStyleSheet(MAIN_STYLE)

    # ── 仓库列表 ─────────────────────────────────────────────────────

    def _load_repos(self):
        self.repo_list.clear()
        for repo in self.repo_manager.repos:
            self._add_repo_item(repo)
        if self.repo_manager.repos:
            self.repo_list.setCurrentItem(self.repo_list.topLevelItem(0))

    def _add_repo_item(self, repo: Repository):
        item = QTreeWidgetItem(self.repo_list)
        item.setData(0, Qt.ItemDataRole.UserRole, repo.path)
        item.setText(0, repo.name)
        item.setIcon(0, get_ui_icon("repo_item"))
        item.setToolTip(0, repo.path)
        self._update_repo_item_style(item, repo)
        # 开始监控文件变化
        self.file_watcher.watch(repo.path)
        return item

    def _update_repo_item_style(self, item, repo: Repository):
        """根据状态更新侧边栏列表项样式"""
        pass  # 后续可以加状态角标

    def _on_search_input_changed(self, _text: str):
        """输入变化时重置防抖定时器"""
        self._search_debounce_timer.start()

    def _do_filter_repos(self):
        """防抖到期后执行实际过滤，去除前后空格"""
        self._filter_repos(self.search_input.text())

    def _filter_repos(self, text: str):
        text = text.strip().lower()
        for i in range(self.repo_list.topLevelItemCount()):
            item = self.repo_list.topLevelItem(i)
            item.setHidden(
                text not in item.text(0).lower()
                if text else False
            )

    def _on_repo_selected(self, current, previous):
        if current is None:
            return
        path = current.data(0, Qt.ItemDataRole.UserRole)
        if path and path != self._current_path:
            self._current_path = path
            self._open_working_copy(path)

    def _open_working_copy(self, path: str):
        if not os.path.exists(path):
            self._set_status(f"路径不存在: {path}")
            return
        if not self.engine.is_working_copy(path):
            QMessageBox.warning(self, "警告", f"不是有效的 SVN 工作副本:\n{path}")
            return
        self.stack.setCurrentWidget(self.wc_browser)
        self.wc_browser.load(path)
        self._set_status(f"已加载: {path}")

    # ── 工作副本操作 ──────────────────────────────────────────────────

    def _add_working_copy(self):
        path = QFileDialog.getExistingDirectory(
            self, "选择 SVN 工作副本目录", os.path.expanduser("~")
        )
        if not path:
            return
        if not self.engine.is_working_copy(path):
            QMessageBox.warning(self, "警告",
                                f"所选目录不是有效的 SVN 工作副本:\n{path}\n\n"
                                "请选择已检出的 SVN 目录，或先通过[检出]功能获取工作副本。")
            return
        # 获取 URL
        info = self.engine.get_info(path)
        url = info.url if info else ""
        repo = self.repo_manager.add(path, url=url)
        item = self._add_repo_item(repo)
        self.repo_list.setCurrentItem(item)
        self._set_status(f"已添加: {repo.name}")

    def _remove_working_copy(self):
        item = self.repo_list.currentItem()
        if not item:
            return
        path = item.data(0, Qt.ItemDataRole.UserRole)
        name = item.text(0)
        reply = QMessageBox.question(
            self, "移除确认",
            f'确定要从列表中移除 [{name}] 吗？\n（不会删除本地文件）',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.repo_manager.remove(path)
            self.file_watcher.unwatch(path)
            idx = self.repo_list.indexOfTopLevelItem(item)
            self.repo_list.takeTopLevelItem(idx)
            if self._current_path == path:
                self._current_path = ""
                self.stack.setCurrentWidget(self.welcome_page)

    def _checkout(self):
        dlg = CheckoutDialog(self.engine, self)
        # 检出成功信号：自动添加到仓库列表
        dlg.checkout_success.connect(self._on_checkout_success)
        dlg.exec()

    def _on_checkout_success(self, url: str, path: str):
        """检出成功后添加到侧边栏"""
        repo = self.repo_manager.add(path, url=url)
        item = self._add_repo_item(repo)
        self.repo_list.setCurrentItem(item)
        self._set_status("检出完成")

    def _do_update(self):
        path = self._current_path or self._get_selected_path()
        if not path:
            return
        self._set_status("正在更新...")
        dlg = UpdateDialog(self.engine, path, self)
        dlg.exec()
        self._refresh_current()

    def _do_commit(self):
        path = self._current_path or self._get_selected_path()
        if not path:
            return
        changed = self.engine.get_changed_files(path)
        if not changed:
            QMessageBox.information(self, "提交", "没有需要提交的修改。")
            return
        dlg = CommitDialog(self.engine, path, changed, self)
        dlg.exec()
        self._refresh_current()

    def _do_revert(self):
        path = self._current_path or self._get_selected_path()
        if not path:
            return
        # 通过浏览器获取选中文件
        selected = self.wc_browser.get_selected_paths()
        if not selected:
            selected = [path]
        reply = QMessageBox.question(
            self, "还原确认",
            f"确定要还原以下文件的修改吗？\n" +
            "\n".join(selected[:5]) +
            ("\n..." if len(selected) > 5 else ""),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            ok, msg = self.engine.revert(selected, recursive=True)
            if ok:
                self._set_status("还原完成")
            else:
                QMessageBox.warning(self, "还原失败", msg)
            self._refresh_current()

    def _do_add(self):
        paths = self.wc_browser.get_selected_paths()
        if not paths:
            self._set_status("请先在文件列表中选择要添加的文件")
            return
        ok, msg = self.engine.add(paths)
        self._set_status("添加成功" if ok else f"添加失败: {msg}")
        self._refresh_current()

    def _do_delete(self):
        paths = self.wc_browser.get_selected_paths()
        if not paths:
            return
        reply = QMessageBox.question(
            self, "删除确认", f"确认删除选中的 {len(paths)} 个文件？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            ok, msg = self.engine.delete(paths, force=True)
            self._set_status("删除成功" if ok else f"删除失败: {msg}")
            self._refresh_current()

    def _do_log(self):
        path = self._get_action_path()
        if not path:
            return
        dlg = LogDialog(self.engine, path, self)
        dlg.exec()

    def _do_diff(self):
        path = self._get_action_path()
        if not path:
            return
        diff_text = self.engine.get_diff(path)
        dlg = DiffViewer(path, diff_text, self)
        dlg.exec()

    def _do_cleanup(self, path: str = None):
        path = path or self._current_path
        if not path:
            return
        self._set_status("正在清理...")
        ok, msg = self.engine.cleanup(path)
        if ok:
            self._set_status("清理完成")
            QMessageBox.information(
                self, "清理完成",
                f"工作副本清理成功：\n{path}\n\n{msg.strip() or '（无额外输出）'}"
            )
        else:
            self._set_status(f"清理失败: {msg}")
            QMessageBox.warning(self, "清理失败", msg)

    def _do_switch(self):
        path = self._current_path
        if not path:
            return
        info = self.engine.get_info(path)
        current_url = info.url if info else ""
        url, ok = QInputDialog.getText(
            self, "切换分支", "输入目标 URL:", text=current_url
        )
        if ok and url:
            self._set_status("正在切换...")
            self._exec_with_auth(
                lambda u, p, nc: self.engine.switch(path, url,
                                                    username=u, password=p,
                                                    no_auth_cache=nc),
                success_status="切换完成",
                error_title="切换失败",
                on_success=self._refresh_current,
            )

    def _do_properties(self):
        path = self._get_action_path()
        if not path:
            return
        dlg = PropertiesDialog(self.engine, path, self)
        dlg.exec()

    def _do_blame(self):
        path = self._get_action_path()
        if not path:
            return
        blame_text = self.engine.blame(path)
        dlg = DiffViewer(path, blame_text, self, title="Blame")
        dlg.exec()

    def _do_resolve_conflict(self):
        """打开冲突解决对话框。
        优先取浏览器中选中的冲突文件；若未选中则扫描整个工作副本的冲突文件。
        """
        path = self._current_path
        if not path:
            return

        # 优先用浏览器已选中的路径（单个文件）
        selected = self.wc_browser.get_selected_paths()
        conflict_path = None

        if selected:
            # 检查选中项是否为冲突文件
            conflict_path = selected[0]
        else:
            # 扫描工作副本，找第一个冲突文件
            conflicts = self.engine.get_conflict_files(path)
            if not conflicts:
                QMessageBox.information(self, "无冲突", "当前工作副本中没有冲突文件。")
                return
            conflict_path = conflicts[0].path

        if not conflict_path or not os.path.isfile(conflict_path):
            QMessageBox.warning(self, "无法解决冲突",
                                "请在文件列表中选择一个冲突文件后再执行此操作。")
            return

        dlg = ConflictDialog(self.engine, conflict_path, self)
        dlg.resolved.connect(lambda _: self._refresh_current())
        dlg.exec()

    def _do_lock(self):
        paths = self.wc_browser.get_selected_paths()
        if not paths:
            return
        lock_msg, ok = QInputDialog.getText(self, "锁定", "锁定备注（可选）：")
        if ok:
            self._exec_with_auth(
                lambda u, p, nc: self.engine.lock(paths, message=lock_msg,
                                                   username=u, password=p,
                                                   no_auth_cache=nc),
                success_status="锁定成功",
                error_title="锁定失败",
                on_success=self._refresh_current,
            )

    def _refresh_current(self):
        if self._current_path:
            self.wc_browser.refresh()

    # ── 上下文菜单 ───────────────────────────────────────────────────

    def _repo_context_menu(self, pos: QPoint):
        item = self.repo_list.itemAt(pos)
        if not item:
            return
        path = item.data(0, Qt.ItemDataRole.UserRole)
        menu = QMenu(self)
        menu.setStyleSheet(MENU_STYLE)

        act = menu.addAction(get_ui_icon("update"),  "更新")
        act.triggered.connect(self._do_update)
        act = menu.addAction(get_ui_icon("commit"),  "提交...")
        act.triggered.connect(self._do_commit)
        menu.addSeparator()
        act = menu.addAction(get_ui_icon("log"),     "查看日志...")
        act.triggered.connect(self._do_log)
        act = menu.addAction(get_ui_icon("diff"),    "查看 Diff...")
        act.triggered.connect(self._do_diff)
        menu.addSeparator()
        act = menu.addAction(get_ui_icon("open_finder"), "在 Finder 中显示")
        act.triggered.connect(lambda: self._reveal_in_finder(path))
        menu.addSeparator()
        act = menu.addAction(get_ui_icon("refresh"), "清理工作副本 (Cleanup)")
        act.triggered.connect(lambda: self._do_cleanup(path))
        menu.addSeparator()
        act = menu.addAction(get_ui_icon("lock"),    "清除已保存的凭证...")
        act.triggered.connect(lambda: self._do_clear_auth(path))
        menu.addSeparator()
        act = menu.addAction(get_ui_icon("rename"),  "重命名")
        act.triggered.connect(lambda: self._rename_repo(item))
        act = menu.addAction(get_ui_icon("remove_repo"), "移除")
        act.triggered.connect(self._remove_working_copy)

        menu.exec(self.repo_list.mapToGlobal(pos))

    def _reveal_in_finder(self, path: str):
        import subprocess
        subprocess.Popen(["open", path])

    def _rename_repo(self, item):
        path = item.data(0, Qt.ItemDataRole.UserRole)
        name, ok = QInputDialog.getText(
            self, "重命名", "新名称：", text=item.text(0)
        )
        if ok and name.strip():
            item.setText(0, name.strip())
            self.repo_manager.update_name(path, name.strip())

    # ── 辅助方法 ─────────────────────────────────────────────────────

    def _get_selected_path(self) -> str:
        item = self.repo_list.currentItem()
        if item:
            return item.data(0, Qt.ItemDataRole.UserRole) or ""
        return ""

    def _get_action_path(self) -> str:
        """优先返回浏览器中选中的文件路径，否则返回工作副本根路径"""
        paths = self.wc_browser.get_selected_paths()
        if paths:
            return paths[0]
        return self._current_path

    def _set_status(self, msg: str):
        self.status_label.setText(msg)

    def _on_file_changed(self, path: str):
        if path == self._current_path:
            QTimer.singleShot(1000, self._refresh_current)

    def _handle_browser_action(self, action: str, paths: list):
        """处理浏览器发出的操作请求"""
        action_map = {
            "commit":  self._do_commit,
            "update":  self._do_update,
            "revert":  self._do_revert,
            "diff":    self._do_diff,
            "log":     self._do_log,
            "add":     self._do_add,
            "delete":  self._do_delete,
            "properties": self._do_properties,
            "lock":    self._do_lock,
            "blame":   self._do_blame,
            "resolve_conflict": self._do_resolve_conflict,
        }
        if action == "cleanup":
            self._do_cleanup(paths[0] if paths else None)
        elif action in action_map:
            action_map[action]()

    def _do_clear_auth(self, path: str = ""):
        """清除本仓库（或全部）已缓存的 SVN 认证凭证"""
        from .auth_clear_dialog import AuthClearDialog
        # 获取该仓库的 repo_root URL 以便精准匹配凭证
        realm_hint = ""
        if path:
            info = self.engine.get_info(path)
            if info:
                realm_hint = info.repo_root or info.url

        dlg = AuthClearDialog(self.engine, realm_hint=realm_hint, parent=self)
        dlg.exec()

    def _show_preferences(self):
        QMessageBox.information(self, "偏好设置", "偏好设置功能即将上线。")

    def _show_about(self):
        QMessageBox.about(self, "关于 SVNFree",
                          "<h2>SVNFree</h2>"
                          "<p>macOS SVN 管理工具，使用 Python + PyQt6 开发。</p>"
                          "<p>功能对标 SnailSVNLite，支持提交、更新、Diff、日志等全部 SVN 操作。</p>")

    # ── 认证辅助 ─────────────────────────────────────────────────────

    _AUTH_KEYWORDS = [
        "authentication", "authorization", "e170001",
        "credentials", "password", "username",
        "realm", "forbidden", "401", "403",
        "no authentication provider",
    ]

    @classmethod
    def _is_auth_error(cls, msg: str) -> bool:
        lower = msg.lower()
        return any(k in lower for k in cls._AUTH_KEYWORDS)

    def _ask_credentials(self, realm: str = "") -> tuple[str, str, bool] | None:
        """弹出认证对话框，返回 (username, password, no_cache) 或 None（用户取消）"""
        dlg = AuthDialog(realm=realm, parent=self)
        if dlg.exec():
            return dlg.get_credentials()
        return None

    def _exec_with_auth(self, fn, success_status: str = "",
                        error_title: str = "操作失败",
                        on_success=None):
        """执行 fn(username, password, no_auth_cache) -> (ok, msg)。
        首次以空凭证执行；若返回认证错误则弹出 AuthDialog 重试一次。
        on_success: 成功后的无参回调。
        """
        ok, msg = fn(None, None, False)
        if not ok and self._is_auth_error(msg):
            creds = self._ask_credentials()
            if creds:
                username, password, no_cache = creds
                ok, msg = fn(username, password, no_cache)
            else:
                self._set_status(f"{error_title}（已取消认证）")
                return

        if ok:
            if success_status:
                self._set_status(success_status)
            if on_success:
                on_success()
        else:
            self._set_status(f"{error_title}: {msg[:60]}")
            QMessageBox.critical(self, error_title, msg)

    def closeEvent(self, event):
        self.file_watcher.stop()
        super().closeEvent(event)
