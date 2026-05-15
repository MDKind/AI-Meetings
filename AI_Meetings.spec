# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for AI Meetings
# Build from repo root:
#   build_venv\Scripts\python.exe -m PyInstaller AI_Meetings.spec --clean

import sys
import os
from pathlib import Path

block_cipher = None

project_root = Path(SPECPATH)

# ── faster-whisper / ctranslate2 assets ───────────────────────────────────────
import ctranslate2
ct2_dir = Path(ctranslate2.__file__).parent
ct2_datas = [(str(ct2_dir), 'ctranslate2')]

# ── sounddevice ───────────────────────────────────────────────────────────────
import sounddevice as _sd
sd_dir = Path(_sd.__file__).parent
sd_datas = [(str(sd_dir), 'sounddevice')]

# ── sv_ttk (Sun Valley theme — TCL files) ────────────────────────────────────
# sv_ttk is no longer used, replaced by flet.
sv_datas = []

all_datas = ct2_datas + sd_datas + sv_datas + [('version.txt', '.')]

# ── Hidden imports ────────────────────────────────────────────────────────────
hidden_imports = [
    # faster-whisper / ctranslate2
    'faster_whisper', 'faster_whisper.audio', 'faster_whisper.tokenizer',
    'faster_whisper.transcribe', 'faster_whisper.utils', 'faster_whisper.vad',
    'ctranslate2',
    'tokenizers',
    'huggingface_hub', 'huggingface_hub.file_download',
    'av', 'av.audio',
    'onnxruntime',
    # Audio
    'sounddevice', 'pyaudiowpatch',
    'comtypes', 'comtypes.client',
    # LLM / networking
    'openai', 'httpx', 'httpcore', 'anyio',
    'requests',
    'tiktoken', 'tiktoken_ext', 'tiktoken_ext.openai_public',
    # UI / stdlib
    'tkinter', 'tkinter.ttk', 'tkinter.messagebox',
    'flet',
    'dotenv', 'numpy',
    # numba/llvmlite needed by some ctranslate2 builds
    'numba', 'llvmlite',
]

a = Analysis(
    ['main.py'],
    pathex=[str(project_root)],
    binaries=[],
    datas=all_datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'torch', 'torchaudio', 'torchvision',
        'whisper',
        'tensorflow', 'keras', 'transformers',
        'pytest', 'unittest',
        'IPython', 'jupyter', 'notebook',
        'matplotlib', 'pandas', 'pyarrow',
        'grpc', 'tensorboard',
        'pydub', 'scipy', 'PIL', 'pillow',
        'pycaw',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='AI_Meetings',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,
    icon='installer\\assets\\icon.ico',
)
