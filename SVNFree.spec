# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller 打包配置 - 生成 SVNFree.app
使用: pyinstaller SVNFree.spec
"""

import os
import sys

block_cipher = None

a = Analysis(
    ['svn_manager/main.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=[
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'watchdog.observers',
        'watchdog.observers.fsevents',
        'watchdog.events',
        'xml.etree.ElementTree',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'scipy', 'numpy', 'matplotlib'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SVNFree',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='SVNFree',
)

app = BUNDLE(
    coll,
    name='SVNFree.app',
    icon='assets/svn.icns',
    bundle_identifier='com.svnfree.app',
    info_plist={
        'NSPrincipalClass': 'NSApplication',
        'NSAppleScriptEnabled': False,
        'CFBundleDisplayName': 'SVNFree',
        'CFBundleVersion': '1.0.0',
        'CFBundleShortVersionString': '1.0.0',
        'NSHighResolutionCapable': True,
        'LSUIElement': False,
        'CFBundleDocumentTypes': [
            {
                'CFBundleTypeName': 'Folder',
                'CFBundleTypeRole': 'Viewer',
                'LSItemContentTypes': ['public.folder'],
            }
        ],
    },
)
