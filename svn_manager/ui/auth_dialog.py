"""
SVN 认证对话框 - 当操作需要用户名/密码时弹出
"""
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QLineEdit, QFormLayout, QCheckBox,
)
from PyQt6.QtCore import Qt
from .theme import MAIN_STYLE


class AuthDialog(QDialog):
    """用户名/密码输入对话框"""

    def __init__(self, realm: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("需要身份验证")
        self.setMinimumWidth(420)
        self.setStyleSheet(MAIN_STYLE)
        self.realm = realm
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        # 标题
        title = QLabel("需要身份验证")
        title.setStyleSheet("font-size:15px;font-weight:700;color:#89b4fa;")
        layout.addWidget(title)

        # 提示信息
        if self.realm:
            hint = QLabel(f"服务器: {self.realm}")
            hint.setStyleSheet("font-size:12px;color:#a6adc8;")
            hint.setWordWrap(True)
            layout.addWidget(hint)

        desc = QLabel("此仓库需要身份验证，请输入用户名和密码：")
        desc.setStyleSheet("font-size:12px;color:#cdd6f4;")
        desc.setWordWrap(True)
        layout.addWidget(desc)

        # 表单
        form = QFormLayout()
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)

        self.username_edit = QLineEdit()
        self.username_edit.setPlaceholderText("用户名")
        form.addRow("用户名：", self.username_edit)

        self.password_edit = QLineEdit()
        self.password_edit.setPlaceholderText("密码")
        self.password_edit.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow("密  码：", self.password_edit)

        layout.addLayout(form)

        # 记住密码（提示用，实际由 svn 自身存储凭证）
        self.remember_cb = QCheckBox("允许 SVN 记住此凭证")
        self.remember_cb.setChecked(True)
        self.remember_cb.setStyleSheet("font-size:12px;color:#a6adc8;")
        layout.addWidget(self.remember_cb)

        # 按钮
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel = QPushButton("取消")
        cancel.setFixedSize(80, 34)
        cancel.clicked.connect(self.reject)
        btn_row.addWidget(cancel)

        ok = QPushButton("确认")
        ok.setObjectName("primaryBtn")
        ok.setFixedSize(80, 34)
        ok.clicked.connect(self.accept)
        btn_row.addWidget(ok)
        layout.addLayout(btn_row)

        # 回车确认
        self.password_edit.returnPressed.connect(self.accept)

    def get_credentials(self) -> tuple[str, str, bool]:
        """返回 (username, password, no_auth_cache)"""
        username = self.username_edit.text()
        password = self.password_edit.text()
        no_cache = not self.remember_cb.isChecked()
        return username, password, no_cache
