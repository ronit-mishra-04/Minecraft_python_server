# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Minecraft Python Server.
Builds three one-file executables:
  - minecraft-server       (installer / setup)
  - minecraft-server-ui    (desktop control panel)
  - minecraft-server-uninstall (uninstaller)

Run on Ubuntu with:
    pyinstaller minecraft_server.spec
"""

import os

block_cipher = None

# ── Common analysis options ─────────────────────────────────────────
common_kwargs = dict(
    pathex=[os.path.abspath('.')],
    binaries=[],
    datas=[],
    hiddenimports=['requests', 'requests.adapters', 'urllib3'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)


# ── 1. minecraft-server  (server.py → installer + setup) ───────────
a_server = Analysis(
    ['server.py'],
    cipher=block_cipher,
    **common_kwargs,
)
pyz_server = PYZ(a_server.pure, cipher=block_cipher)
exe_server = EXE(
    pyz_server,
    a_server.scripts,
    a_server.binaries,
    a_server.datas,
    [],
    name='minecraft-server',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
)


# ── 2. minecraft-server-ui  (server_ui.py → control panel) ─────────
a_ui = Analysis(
    ['server_ui.py'],
    cipher=block_cipher,
    **common_kwargs,
)
pyz_ui = PYZ(a_ui.pure, cipher=block_cipher)
exe_ui = EXE(
    pyz_ui,
    a_ui.scripts,
    a_ui.binaries,
    a_ui.datas,
    [],
    name='minecraft-server-ui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
)


# ── 3. minecraft-server-uninstall  (uninstall.py) ───────────────────
a_uninstall = Analysis(
    ['uninstall.py'],
    cipher=block_cipher,
    **common_kwargs,
)
pyz_uninstall = PYZ(a_uninstall.pure, cipher=block_cipher)
exe_uninstall = EXE(
    pyz_uninstall,
    a_uninstall.scripts,
    a_uninstall.binaries,
    a_uninstall.datas,
    [],
    name='minecraft-server-uninstall',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
)
