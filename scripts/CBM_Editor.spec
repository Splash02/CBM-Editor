# -*- mode: python ; coding: utf-8 -*-

from PyInstaller import __version__ as pyinstaller_version
import os
import sys

if tuple(int(part) for part in pyinstaller_version.split('.')[:2]) < (6, 21):
    raise RuntimeError('CBM Editor requires PyInstaller 6.21 or newer')

project_root = os.path.dirname(SPECPATH)
if os.path.basename(project_root).lower() == 'scripts':
    project_root = os.path.dirname(project_root)
edition = os.environ.get('CBM_BUILD_EDITION', 'preview').strip().lower()
if edition not in {'preview', 'release'}:
    raise RuntimeError('CBM_BUILD_EDITION must be preview or release')
is_preview = edition == 'preview'
entry_file = os.path.join(project_root, 'scripts', 'CBM_Editor_preview.py' if is_preview else 'CBM_Editor_release.py')
output_name = 'CBM_Editor_PREVIEW' if is_preview else 'CBM_Editor'
icon_file = os.path.join(project_root, 'scripts', 'icon_pre.ico' if is_preview else 'icon.ico')

if sys.platform.startswith('win'):
    platform_binaries = [
        (os.path.join(project_root, 'cbm_editor/vendor/bass/win-x64/bass.dll'), 'cbm_editor/vendor/bass/win-x64'),
        (os.path.join(project_root, 'cbm_editor/vendor/bass/win-x64/bassalac.dll'), 'cbm_editor/vendor/bass/win-x64'),
        (os.path.join(project_root, 'cbm_editor/vendor/bass/win-x64/bassenc.dll'), 'cbm_editor/vendor/bass/win-x64'),
        (os.path.join(project_root, 'cbm_editor/vendor/bass/win-x64/bassenc_mp3.dll'), 'cbm_editor/vendor/bass/win-x64'),
        (os.path.join(project_root, 'cbm_editor/vendor/bass/win-x64/bassflac.dll'), 'cbm_editor/vendor/bass/win-x64'),
        (os.path.join(project_root, 'cbm_editor/vendor/bass/win-x64/bassmix.dll'), 'cbm_editor/vendor/bass/win-x64'),
        (os.path.join(project_root, 'cbm_editor/vendor/bass/win-x64/bassopus.dll'), 'cbm_editor/vendor/bass/win-x64'),
    ]
elif sys.platform.startswith('linux'):
    platform_binaries = [
        (os.path.join(project_root, 'cbm_editor/vendor/bass/linux-x86_64/libbass.so'), 'cbm_editor/vendor/bass/linux-x86_64'),
        (os.path.join(project_root, 'cbm_editor/vendor/bass/linux-x86_64/libbassalac.so'), 'cbm_editor/vendor/bass/linux-x86_64'),
        (os.path.join(project_root, 'cbm_editor/vendor/bass/linux-x86_64/libbassenc.so'), 'cbm_editor/vendor/bass/linux-x86_64'),
        (os.path.join(project_root, 'cbm_editor/vendor/bass/linux-x86_64/libbassenc_mp3.so'), 'cbm_editor/vendor/bass/linux-x86_64'),
        (os.path.join(project_root, 'cbm_editor/vendor/bass/linux-x86_64/libbassflac.so'), 'cbm_editor/vendor/bass/linux-x86_64'),
        (os.path.join(project_root, 'cbm_editor/vendor/bass/linux-x86_64/libbassmix.so'), 'cbm_editor/vendor/bass/linux-x86_64'),
        (os.path.join(project_root, 'cbm_editor/vendor/bass/linux-x86_64/libbassopus.so'), 'cbm_editor/vendor/bass/linux-x86_64'),
    ]
else:
    raise RuntimeError(f'Unsupported BASS platform: {sys.platform}')


a = Analysis(
    [entry_file],
    pathex=[project_root],
    binaries=platform_binaries,
    datas=[
        (os.path.join(project_root, 'cbm_editor/sounds'), 'cbm_editor/sounds'),
        (os.path.join(project_root, 'cbm_editor/fonts'), 'cbm_editor/fonts'),
        (os.path.join(project_root, 'cbm_editor/vendor/bass/manifest.json'), 'cbm_editor/vendor/bass'),
        (os.path.join(project_root, 'cbm_editor/vendor/bass/LICENSE.txt'), 'cbm_editor/vendor/bass'),
        (os.path.join(project_root, 'cbm_editor/vendor/bass/LICENSE_BASSALAC.txt'), 'cbm_editor/vendor/bass'),
        (os.path.join(project_root, 'cbm_editor/vendor/bass/LICENSE_BASSENC.txt'), 'cbm_editor/vendor/bass'),
        (os.path.join(project_root, 'cbm_editor/vendor/bass/LICENSE_BASSENC_MP3.txt'), 'cbm_editor/vendor/bass'),
        (os.path.join(project_root, 'cbm_editor/vendor/bass/LICENSE_BASSFLAC.txt'), 'cbm_editor/vendor/bass'),
        (os.path.join(project_root, 'cbm_editor/vendor/bass/LICENSE_BASSMIX.txt'), 'cbm_editor/vendor/bass'),
        (os.path.join(project_root, 'cbm_editor/vendor/bass/LICENSE_BASSOPUS.txt'), 'cbm_editor/vendor/bass'),
        (os.path.join(project_root, 'cbm_editor/vendor/bass/THIRD_PARTY_NOTICES.txt'), 'cbm_editor/vendor/bass'),
    ],
    hiddenimports=[],
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
    name=output_name,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[icon_file],
)
