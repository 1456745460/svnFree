"""
SVN 凭证管理对话框
列出本地已缓存的认证信息，支持单条或全部清除，以便重新输入用户名密码。
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTreeWidget, QTreeWidgetItem,
    QMessageBox, QHeaderView,
)
from PyQt6.QtCore import Qt, QSize
from .theme import MAIN_STYLE


class AuthClearDialog(QDialog):
    def __init__(self, engine, realm_hint: str = "", parent=None):
        super().__init__(parent)
        self.engine = engine
        self.realm_hint = realm_hint
        self.setWindowTitle("管理已保存的凭证")
        self.setMinimumWidth(560)
        self.setMinimumHeight(360)
        self.setStyleSheet(MAIN_STYLE)
        self._setup_ui()
        self._load_entries()

    # ── UI 构建 ────────────────────────────────────────────────────

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # 标题
        title = QLabel("已保存的 SVN 认证凭证")
        title.setStyleSheet("font-size:15px;font-weight:700;color:#89b4fa;")
        layout.addWidget(title)

        # 说明
        desc = QLabel(
            "以下是本机缓存的 SVN 认证信息（存储于 ~/.subversion/auth/）。\n"
            "清除后，下次访问该仓库时将重新提示输入用户名和密码。"
        )
        desc.setStyleSheet("font-size:12px;color:#a6adc8;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 凭证列表
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["服务器 / Realm", "用户名"])
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setStyleSheet("""
            QTreeWidget {
                background:#111117; color:#cdd6f4;
                border:1px solid #313244; border-radius:4px;
                font-size:12px;
            }
            QTreeWidget::item { height:32px; padding:0 6px; }
            QTreeWidget::item:selected { background:#313244; }
            QTreeWidget::item:hover:!selected { background:#1e1e2e; }
            QHeaderView::section {
                background:#1e1e2e; color:#89b4fa;
                border:none; border-bottom:1px solid #313244;
                padding:4px 6px; font-size:12px;
            }
        """)
        layout.addWidget(self.tree, 1)

        # 状态文字
        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("font-size:12px;color:#a6adc8;")
        layout.addWidget(self.status_lbl)

        # 按钮行
        btn_row = QHBoxLayout()

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setFixedSize(80, 34)
        self.refresh_btn.clicked.connect(self._load_entries)
        btn_row.addWidget(self.refresh_btn)

        btn_row.addStretch()

        self.clear_sel_btn = QPushButton("清除选中")
        self.clear_sel_btn.setFixedSize(96, 34)
        self.clear_sel_btn.clicked.connect(self._clear_selected)
        btn_row.addWidget(self.clear_sel_btn)

        self.clear_all_btn = QPushButton("清除全部")
        self.clear_all_btn.setObjectName("primaryBtn")
        self.clear_all_btn.setFixedSize(96, 34)
        self.clear_all_btn.clicked.connect(self._clear_all)
        btn_row.addWidget(self.clear_all_btn)

        close_btn = QPushButton("关闭")
        close_btn.setFixedSize(80, 34)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        layout.addLayout(btn_row)

    # ── 数据加载 ───────────────────────────────────────────────────

    def _load_entries(self):
        self.tree.clear()
        entries = self.engine.list_auth_cache()

        # 若有 realm_hint，将匹配的排在最前
        if self.realm_hint:
            hint_lower = self.realm_hint.lower()
            matched = [e for e in entries if hint_lower in e.get("realm", "").lower()]
            others  = [e for e in entries if hint_lower not in e.get("realm", "").lower()]
            entries = matched + others

        for entry in entries:
            item = QTreeWidgetItem(self.tree)
            realm = entry.get("realm", "（未知）")
            username = entry.get("username", "（未知）")
            item.setText(0, realm)
            item.setText(1, username)
            item.setData(0, Qt.ItemDataRole.UserRole, entry)

            # 高亮当前仓库匹配的条目
            if self.realm_hint and self.realm_hint.lower() in realm.lower():
                item.setForeground(0, __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor("#a6e3a1"))
                item.setForeground(1, __import__("PyQt6.QtGui", fromlist=["QColor"]).QColor("#a6e3a1"))

        count = self.tree.topLevelItemCount()
        self.status_lbl.setText(f"共 {count} 条缓存凭证" + (
            f"（当前仓库匹配条目已高亮显示）" if self.realm_hint else ""
        ))
        self.clear_sel_btn.setEnabled(count > 0)
        self.clear_all_btn.setEnabled(count > 0)

    # ── 操作 ───────────────────────────────────────────────────────

    def _clear_selected(self):
        items = self.tree.selectedItems()
        if not items:
            self.status_lbl.setText("请先选择要清除的条目")
            return

        reply = QMessageBox.question(
            self, "确认清除",
            f"确定要清除选中的 {len(items)} 条凭证吗？\n下次访问对应仓库时将重新要求输入用户名密码。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        fail_msgs = []
        for item in items:
            entry = item.data(0, Qt.ItemDataRole.UserRole)
            realm = entry.get("realm", "")
            file_path = entry.get("_file", "")

            if file_path:
                # 文件扫描模式：直接删除文件
                import os
                try:
                    os.remove(file_path)
                except Exception as e:
                    fail_msgs.append(str(e))
            else:
                # svn auth 模式
                ok, msg = self.engine.clear_auth_cache(realm)
                if not ok:
                    fail_msgs.append(msg)

        if fail_msgs:
            QMessageBox.warning(self, "部分失败", "\n".join(fail_msgs))
        else:
            self.status_lbl.setText(f"已清除 {len(items)} 条凭证")

        self._load_entries()

    def _clear_all(self):
        count = self.tree.topLevelItemCount()
        if count == 0:
            return
        reply = QMessageBox.question(
            self, "确认清除全部",
            f"确定要清除全部 {count} 条已保存的 SVN 凭证吗？\n"
            "所有仓库下次访问时都将重新要求输入用户名密码。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        ok, msg = self.engine.clear_auth_cache("")
        if ok:
            self.status_lbl.setText(msg)
        else:
            QMessageBox.warning(self, "清除失败", msg)
        self._load_entries()
