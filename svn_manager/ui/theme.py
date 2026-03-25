"""
UI 主题样式表
"""

MAIN_STYLE = """
QMainWindow, QDialog {
    background-color: #1e1e2e;
    color: #cdd6f4;
}

QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: ".AppleSystemUIFont", "PingFang SC", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}

/* ── 菜单栏 ── */
QMenuBar {
    background-color: #181825;
    color: #cdd6f4;
    border-bottom: 1px solid #313244;
}
QMenuBar::item:selected {
    background-color: #45475a;
    border-radius: 4px;
}
QMenu {
    background-color: #24273a;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 5px 20px 5px 8px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #363a4f;
}
QMenu::separator {
    height: 1px;
    background: #45475a;
    margin: 4px 8px;
}

/* ── 工具栏 ── */
QToolBar {
    background-color: #181825;
    border-bottom: 1px solid #313244;
    spacing: 4px;
    padding: 4px 8px;
}
QToolButton {
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 6px 10px;
    color: #cdd6f4;
    font-size: 12px;
}
QToolButton:hover {
    background-color: #313244;
}
QToolButton:pressed {
    background-color: #45475a;
}

/* ── 分割器 ── */
QSplitter::handle {
    background-color: #313244;
}

/* ── 树视图 ── */
QTreeWidget, QTreeView {
    background-color: #181825;
    alternate-background-color: #1e1e2e;
    border: none;
    outline: none;
    color: #cdd6f4;
}
QTreeWidget::item, QTreeView::item {
    height: 26px;
    padding-left: 4px;
    border-radius: 4px;
}
QTreeWidget::item:hover, QTreeView::item:hover {
    background-color: #313244;
}
QTreeWidget::item:selected, QTreeView::item:selected {
    background-color: #45475a;
    color: #cdd6f4;
}
QTreeWidget::branch {
    background: transparent;
}

/* ── 列表视图 ── */
QListWidget, QListView {
    background-color: #181825;
    border: none;
    outline: none;
    color: #cdd6f4;
}
QListWidget::item, QListView::item {
    height: 28px;
    padding: 2px 8px;
    border-radius: 4px;
}
QListWidget::item:hover {
    background-color: #313244;
}
QListWidget::item:selected {
    background-color: #45475a;
    color: #cdd6f4;
}

/* ── 表格 ── */
QTableWidget, QTableView {
    background-color: #181825;
    alternate-background-color: #1e1e2e;
    gridline-color: #313244;
    border: none;
    outline: none;
    color: #cdd6f4;
}
QTableWidget::item, QTableView::item {
    padding: 4px 8px;
}
QTableWidget::item:selected, QTableView::item:selected {
    background-color: #45475a;
    color: #cdd6f4;
}
QHeaderView::section {
    background-color: #181825;
    color: #a6adc8;
    border: none;
    border-right: 1px solid #313244;
    border-bottom: 1px solid #313244;
    padding: 6px 8px;
    font-weight: 600;
}

/* ── 按钮 ── */
QPushButton {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 6px 16px;
    font-size: 13px;
}
/* 固定尺寸的小图标按钮，不能让全局 padding 撑变形 */
QPushButton#addBtn,
QPushButton[flat="true"] {
    padding: 0px;
}
QPushButton:hover {
    background-color: #45475a;
    border-color: #585b70;
}
QPushButton:pressed {
    background-color: #585b70;
}
QPushButton:disabled {
    color: #6c7086;
    border-color: #313244;
}
QPushButton#primaryBtn {
    background-color: #89b4fa;
    color: #1e1e2e;
    border-color: #89b4fa;
    font-weight: 600;
}
QPushButton#primaryBtn:hover {
    background-color: #b4befe;
}
QPushButton#dangerBtn {
    background-color: #f38ba8;
    color: #1e1e2e;
    border-color: #f38ba8;
    font-weight: 600;
}
QPushButton#dangerBtn:hover {
    background-color: #eba0ac;
}

/* ── 输入框 ── */
QLineEdit, QTextEdit, QPlainTextEdit {
    background-color: #181825;
    color: #cdd6f4;
    border: 1px solid #313244;
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: #45475a;
}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border-color: #89b4fa;
}

/* ── 下拉框 ── */
QComboBox {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 4px 8px;
}
QComboBox:hover { border-color: #585b70; }
QComboBox::drop-down { border: none; width: 20px; }
QComboBox QAbstractItemView {
    background-color: #24273a;
    border: 1px solid #45475a;
    border-radius: 6px;
    color: #cdd6f4;
    selection-background-color: #45475a;
}

/* ── 滚动条 ── */
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 0;
}
QScrollBar::handle:vertical {
    background: #45475a;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover { background: #585b70; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal {
    background: transparent;
    height: 8px;
    margin: 0;
}
QScrollBar::handle:horizontal {
    background: #45475a;
    border-radius: 4px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover { background: #585b70; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }

/* ── 标签页 ── */
QTabWidget::pane {
    border: 1px solid #313244;
    border-radius: 6px;
    background: #1e1e2e;
}
QTabBar::tab {
    background: #181825;
    color: #a6adc8;
    padding: 8px 16px;
    border: 1px solid #313244;
    border-bottom: none;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    margin-right: 2px;
}
QTabBar::tab:selected {
    background: #1e1e2e;
    color: #cdd6f4;
    border-bottom: 2px solid #89b4fa;
}
QTabBar::tab:hover:!selected { background: #313244; }

/* ── 状态栏 ── */
QStatusBar {
    background: #181825;
    color: #a6adc8;
    border-top: 1px solid #313244;
}

/* ── 分组框 ── */
QGroupBox {
    border: 1px solid #313244;
    border-radius: 6px;
    margin-top: 16px;
    padding-top: 12px;
    color: #a6adc8;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
}

/* ── 复选框 ── */
QCheckBox {
    color: #cdd6f4;
    spacing: 6px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #45475a;
    border-radius: 3px;
    background: #313244;
}
QCheckBox::indicator:checked {
    background: #89b4fa;
    border-color: #89b4fa;
}

/* ── 进度条 ── */
QProgressBar {
    background: #313244;
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background: #89b4fa;
    border-radius: 4px;
}

/* ── 标签 ── */
QLabel {
    color: #cdd6f4;
    background: transparent;
}
QLabel#titleLabel {
    font-size: 15px;
    font-weight: 700;
    color: #cdd6f4;
}
QLabel#subtitleLabel {
    font-size: 12px;
    color: #a6adc8;
}

/* ── 侧边栏 ── */
QWidget#sidebar {
    background-color: #181825;
    border-right: 1px solid #313244;
}

/* ── 内容区 ── */
QWidget#contentArea {
    background-color: #1e1e2e;
}

/* ── diff 查看器 ── */
QPlainTextEdit#diffView {
    font-family: "SF Mono", "JetBrains Mono", Menlo, Monaco, monospace;
    font-size: 12px;
    background: #181825;
    color: #cdd6f4;
    border: none;
}

/* ── 工具提示 ── */
QToolTip {
    background-color: #313244;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 4px;
    padding: 4px 8px;
}
"""

# 独立的右键菜单样式（不含 QWidget 全局规则，避免干扰图标渲染）
MENU_STYLE = """
QMenu {
    background-color: #24273a;
    color: #cdd6f4;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 4px;
    font-family: "PingFang SC", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}
QMenu::item {
    padding: 5px 20px 5px 8px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #363a4f;
    color: #cdd6f4;
}
QMenu::item:disabled {
    color: #6c7086;
}
QMenu::separator {
    height: 1px;
    background: #45475a;
    margin: 4px 8px;
}
"""

# 状态颜色映射
STATUS_COLORS = {
    "modified":    "#a6e3a1",   # 绿色
    "added":       "#89dceb",   # 青色
    "deleted":     "#f38ba8",   # 红色
    "conflicted":  "#fab387",   # 橙色
    "unversioned": "#a6adc8",   # 灰色
    "missing":     "#f38ba8",   # 红色
    "replaced":    "#cba6f7",   # 紫色
    "ignored":     "#585b70",   # 深灰
    "normal":      "#cdd6f4",   # 默认白
    "external":    "#f9e2af",   # 黄色
}

STATUS_LABELS = {
    "modified":    "已修改",
    "added":       "已添加",
    "deleted":     "已删除",
    "conflicted":  "冲突",
    "unversioned": "未添加",
    "missing":     "丢失",
    "replaced":    "已替换",
    "ignored":     "已忽略",
    "normal":      "无变更",
    "external":    "外部",
    "obstructed":  "受阻",
    "unknown":     "未知",
}
