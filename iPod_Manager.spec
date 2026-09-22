# -*- mode: python ; coding: utf-8 -*-
import os
import customtkinter

ctk_path = os.path.dirname(customtkinter.__file__)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        (ctk_path, 'customtkinter'),
    ],
    hiddenimports=[
        'customtkinter',
        'mutagen',
        'mutagen.mp4',
        'mutagen.mp3',
        'mutagen.id3',
        'PIL',
        'PIL._tkinter_finder',
        'yt_dlp',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='iPod Manager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='iPod Manager',
)

app = BUNDLE(
    coll,
    name='iPod Manager.app',
    icon=None,
    bundle_identifier='de.olomek.ipodmanager',
    info_plist={
        'NSHighResolutionCapable': True,
        'CFBundleShortVersionString': '1.0',
        'CFBundleName': 'iPod Manager',
        'NSAppleEventsUsageDescription': 'Für die iPod-Verwaltung benötigt.',
    },
)
