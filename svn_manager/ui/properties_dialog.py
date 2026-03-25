"""
属性对话框
"""
import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem,
    QHeaderView, QTextEdit, QSplitter, QFrame,
    QInputDialog, QMessageBox,
)
from PyQt6.QtCore import Qt
from .theme import MAIN_STYLE
from ..core.svn_engine import SVNEngine


class PropertiesDialog(QDialog):
    def __init__(self, engine: SVNEngine, path: str, parent=None):
        super().__init__(parent)
        self.engine = engine
        self.path = path
        self.setWindowTitle(f"属性 — {os.path.basename(path)}")
        self.setMinimumSize(560, 420)
        self.setStyleSheet(MAIN_STYLE)
        self._setup_ui()
        self._load_props()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)

        path_label = QLabel(self.path)
        path_label.setStyleSheet("color:#89b4fa;font-size:12px;")
        path_label.setWordWrap(True)
        layout.addWidget(path_label)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["属性名", "属性值"])
        self.table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Fixed)
        self.table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.table.setColumnWidth(0, 180)
        self.table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers)
        self.table.currentCellChanged.connect(self._on_row_changed)
        self.table.setStyleSheet("""
            QTableWidget{background:#181825;alternate-background-color:#1a1a2e;
                border:1px solid #313244;border-radius:4px;outline:none;}
            QTableWidget::item{padding:4px 8px;}
            QTableWidget::item:selected{background:#313244;}
            QHeaderView::section{background:#111117;color:#a6adc8;
                border:none;border-bottom:1px solid #313244;padding:4px 8px;}
        """)
        layout.addWidget(self.table)

        self.value_edit = QTextEdit()
        self.value_edit.setReadOnly(True)
        self.value_edit.setMaximumHeight(80)
        self.value_edit.setStyleSheet(
            "background:#111117;color:#cdd6f4;border:1px solid #313244;"
            "border-radius:4px;font-size:12px;")
        layout.addWidget(self.value_edit)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("添加属性")
        add_btn.setFixedHeight(30)
        add_btn.clicked.connect(self._add_prop)
        btn_row.addWidget(add_btn)
        del_btn = QPushButton("删除属性")
        del_btn.setFixedHeight(30)
        del_btn.clicked.connect(self._del_prop)
        btn_row.addWidget(del_btn)
        btn_row.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.setFixedSize(80, 30)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

    def _load_props(self):
        props = self.engine.proplist(self.path)
        self.table.setRowCount(0)
        for name, value in props.items():
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(name))
            self.table.setItem(row, 1, QTableWidgetItem(value[:80]))
            self.table.item(row, 0).setData(
                Qt.ItemDataRole.UserRole, value)

    def _on_row_changed(self, row, col, prev_row, prev_col):
        item = self.table.item(row, 0)
        if item:
            value = item.data(Qt.ItemDataRole.UserRole) or ""
            self.value_edit.setPlainText(value)

    def _add_prop(self):
        name, ok = QInputDialog.getText(self, "添加属性", "属性名：")
        if not ok or not name.strip():
            return
        value, ok2 = QInputDialog.getText(self, "属性值", "属性值：")
        if not ok2:
            return
        success, msg = self.engine.propset(name.strip(), value, self.path)
        if success:
            self._load_props()
        else:
            QMessageBox.warning(self, "失败", msg)

    def _del_prop(self):
        row = self.table.currentRow()
        if row < 0:
            return
        name = self.table.item(row, 0).text()
        ok, msg = self.engine.propset(name, "", self.path)
        if ok:
            self._load_props()
        else:
            QMessageBox.warning(self, "删除失败", msg)
