# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['client_discord.py'],
    pathex=[],
    binaries=[],
    datas=[('C:\\Users\\s2gri\\PycharmProjects\\GGChatPy\\.venv\\Lib\\site-packages\\irc\\codes.txt', 'irc'), ('alert.wav', '.'), ('gg_fUv_icon.ico', '.'), ('notify.mp3', '.'), ('dist/webview_launcher.exe', '.')],
    hiddenimports=['webview'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='GGChat',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    icon='gg_fUv_icon.ico',
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version='version_info.txt',
)
