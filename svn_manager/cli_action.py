"""
CLI 动作入口 - 被 Finder 服务或命令行调用，弹出对应对话框
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt


def main():
    if len(sys.argv) < 2:
        print("用法: cli_action.py <action> [paths...]")
        sys.exit(1)

    action = sys.argv[1]
    paths = sys.argv[2:] if len(sys.argv) > 2 else []

    app = QApplication(sys.argv)
    app.setApplicationName("SVNFree")
    app.setStyle("Fusion")

    from svn_manager.core.svn_engine import SVNEngine
    engine = SVNEngine()

    if not paths:
        print("未指定路径")
        sys.exit(1)

    path = paths[0]

    if action == "commit":
        from svn_manager.ui.commit_dialog import CommitDialog
        changed = engine.get_changed_files(path)
        if not changed:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(None, "提交", "没有需要提交的修改。")
        else:
            dlg = CommitDialog(engine, path, changed)
            dlg.exec()

    elif action == "update":
        from svn_manager.ui.update_dialog import UpdateDialog
        dlg = UpdateDialog(engine, path)
        dlg.exec()

    elif action == "diff":
        from svn_manager.ui.diff_viewer import DiffViewer
        diff = engine.get_diff(path)
        dlg = DiffViewer(path, diff)
        dlg.exec()

    elif action == "log":
        from svn_manager.ui.log_dialog import LogDialog
        dlg = LogDialog(engine, path)
        dlg.exec()

    elif action == "revert":
        from PyQt6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            None, "还原", f"确定要还原修改吗？\n{path}",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            ok, msg = engine.revert(paths, recursive=True)
            QMessageBox.information(None, "还原", "还原成功" if ok else msg)

    elif action == "add":
        ok, msg = engine.add(paths)
        from PyQt6.QtWidgets import QMessageBox
        QMessageBox.information(None, "添加", "添加成功" if ok else msg)

    elif action == "blame":
        from svn_manager.ui.diff_viewer import DiffViewer
        blame = engine.blame(path)
        dlg = DiffViewer(path, blame, title="Blame")
        dlg.exec()

    else:
        # 未知操作，打开主窗口
        from svn_manager.ui.main_window import MainWindow
        window = MainWindow()
        window.show()
        app.exec()
        return

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
