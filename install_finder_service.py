#!/usr/bin/env python3
"""
安装 macOS Finder 服务菜单（右键菜单集成）
在 Finder 中选择文件/文件夹右键即可看到 SVNFree 操作菜单
"""
import os
import sys
import subprocess
import plistlib

SERVICES_DIR = os.path.expanduser("~/Library/Services")
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
VENV_PYTHON = os.path.join(SCRIPT_DIR, "venv", "bin", "python3")
CLI_SCRIPT = os.path.join(SCRIPT_DIR, "svn_manager", "cli_action.py")

ACTIONS = [
    ("SVNFree - 提交",    "commit"),
    ("SVNFree - 更新",    "update"),
    ("SVNFree - 查看Diff", "diff"),
    ("SVNFree - 查看日志", "log"),
    ("SVNFree - 还原",    "revert"),
    ("SVNFree - 添加",    "add"),
]


def create_workflow(name: str, action: str) -> str:
    """创建 .workflow 包（Automator Quick Action）"""
    workflow_dir = os.path.join(SERVICES_DIR, f"{name}.workflow")
    contents_dir = os.path.join(workflow_dir, "Contents")
    os.makedirs(contents_dir, exist_ok=True)

    script_path = os.path.join(contents_dir, "document.wflow")

    # Automator workflow plist
    workflow_plist = {
        "AMApplicationBuild": "521",
        "AMApplicationVersion": "2.10",
        "AMDocumentVersion": "2",
        "actions": [
            {
                "action": {
                    "AMAccepts": {
                        "Container": "List",
                        "Optional": False,
                        "Types": ["com.apple.cocoa.path"],
                    },
                    "AMActionVersion": "2.0.3",
                    "AMApplication": ["Finder"],
                    "AMParameterProperties": {
                        "COMMAND_STRING": {},
                        "SOURCE_STREAM_ONLY": {},
                        "shell": {},
                    },
                    "AMProvides": {
                        "Container": "List",
                        "Types": ["com.apple.cocoa.string"],
                    },
                    "ActionBundlePath": (
                        "/System/Library/Automator/"
                        "Run Shell Script.action"
                    ),
                    "ActionName": "Run Shell Script",
                    "ActionParameters": {
                        "COMMAND_STRING": (
                            f'"{VENV_PYTHON}" "{CLI_SCRIPT}" {action} "$@"'
                        ),
                        "SOURCE_STREAM_ONLY": True,
                        "shell": "/bin/bash",
                    },
                    "BundleIdentifier": (
                        "com.apple.automator.runshelllscript"
                    ),
                    "CFBundleVersion": "2.0.3",
                    "CanShowSelectedItemsWhenRun": True,
                    "CanShowWhenRun": True,
                    "Category": ["AMCategoryUtilities"],
                    "Class Name": "RunShellScriptAction",
                    "InputUUID": "A1B2C3D4-E5F6-7890-ABCD-EF1234567890",
                    "Keywords": ["Shell", "Script"],
                    "OutputUUID": "B2C3D4E5-F6A7-8901-BCDE-F12345678901",
                    "UUID": "C3D4E5F6-A7B8-9012-CDEF-123456789012",
                    "UnlocalizedApplications": ["Automator"],
                    "arguments": {},
                    "isViewVisible": True,
                    "location": "349.500000:579.000000",
                    "nibPath": (
                        "/System/Library/Automator/"
                        "Run Shell Script.action/Contents/Resources/English.lproj/"
                        "main.nib"
                    ),
                },
                "isViewVisible": True,
            }
        ],
        "connectors": {},
        "workflowMetaData": {
            "applicationBundleIDsByPath": {},
            "applicationPaths": [],
            "inputTypeIdentifier": "com.apple.automator.fileSystemObject",
            "outputTypeIdentifier": "com.apple.automator.nothing",
            "presentationMode": 11,
            "processesInput": True,
            "serviceApplicationBundleID": "com.apple.finder",
            "serviceApplicationPath": "/System/Library/CoreServices/Finder.app",
            "serviceInputTypeIdentifier": "com.apple.automator.fileSystemObject",
            "serviceOutputTypeIdentifier": "com.apple.automator.nothing",
            "serviceProcessesInput": True,
            "workflowTypeIdentifier": "com.apple.automator.servicesMenu",
        },
    }

    with open(script_path, "wb") as f:
        plistlib.dump(workflow_plist, f, fmt=plistlib.FMT_XML)

    print(f"  已创建: {workflow_dir}")
    return workflow_dir


def uninstall():
    """卸载所有 SVNFree 服务"""
    import shutil
    count = 0
    if os.path.exists(SERVICES_DIR):
        for item in os.listdir(SERVICES_DIR):
            if item.startswith("SVNFree"):
                path = os.path.join(SERVICES_DIR, item)
                shutil.rmtree(path)
                print(f"  已删除: {path}")
                count += 1
    print(f"已卸载 {count} 个服务。")


def install():
    os.makedirs(SERVICES_DIR, exist_ok=True)
    print(f"安装 Finder 服务到: {SERVICES_DIR}")
    print(f"Python: {VENV_PYTHON}")
    print(f"CLI脚本: {CLI_SCRIPT}")
    print()

    if not os.path.exists(VENV_PYTHON):
        print(f"[错误] 找不到 venv Python: {VENV_PYTHON}")
        print("请先运行: python3 -m venv venv && source venv/bin/activate && pip install PyQt6")
        sys.exit(1)

    if not os.path.exists(CLI_SCRIPT):
        print(f"[错误] 找不到 CLI 脚本: {CLI_SCRIPT}")
        sys.exit(1)

    for name, action in ACTIONS:
        create_workflow(name, action)

    # 刷新服务数据库
    try:
        subprocess.run(["/System/Library/CoreServices/pbs", "-update"],
                       capture_output=True, timeout=10)
        print()
        print("[服务数据库已刷新]")
    except Exception as e:
        print(f"[提示] 刷新服务数据库失败（手动重启 Finder 即可）: {e}")

    print()
    print("=" * 60)
    print("安装完成！")
    print()
    print("后续步骤（必须手动操作）：")
    print()
    print("1. 打开 [系统设置] -> [键盘] -> [键盘快捷键]")
    print("   -> 左侧选 [服务] -> 右侧找到 SVNFree 相关项目，勾选启用")
    print()
    print("   macOS Ventura/Sonoma 路径:")
    print("   系统设置 -> 通用 -> 登录项 (或直接搜索 [服务])")
    print()
    print("2. 也可以打开 Automator.app，直接双击")
    print(f"   {SERVICES_DIR}/SVNFree - 提交.workflow")
    print("   点击顶部 [运行] 按钮验证")
    print()
    print("3. 重启 Finder：")
    print("   按住 Option 键，右键点击 Dock 上的 Finder -> [重新启动]")
    print()
    print("之后在 Finder 中右键文件/文件夹 -> [服务] 即可看到 SVNFree 菜单")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "uninstall":
        uninstall()
    else:
        install()
