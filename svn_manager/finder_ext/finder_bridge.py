"""
Finder 集成 - 通过 macOS Automator Quick Action 或 Services 实现右键菜单
这个脚本作为 CLI 工具被 macOS 服务菜单调用

安装方式：运行 install_finder_service.py
"""
import sys
import os
import subprocess
import argparse


def get_svnfree_python() -> str:
    """获取 SVNFree venv 的 Python 路径"""
    script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    venv_python = os.path.join(script_dir, "..", "venv", "bin", "python3")
    if os.path.exists(venv_python):
        return os.path.abspath(venv_python)
    return sys.executable


def call_svnfree(action: str, paths: list[str]):
    """通过 subprocess 调用 SVNFree GUI"""
    python = get_svnfree_python()
    script = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "svn_manager", "cli_action.py"
    )
    cmd = [python, script, action] + paths
    subprocess.Popen(cmd)


def main():
    parser = argparse.ArgumentParser(description="SVNFree Finder 集成")
    parser.add_argument("action", help="操作: commit/update/diff/log/revert/add")
    parser.add_argument("paths", nargs="*", help="文件路径")
    args = parser.parse_args()
    call_svnfree(args.action, args.paths)


if __name__ == "__main__":
    main()
