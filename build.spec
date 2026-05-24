# PyInstaller 打包配置 —— mincc
#
# 命令：uv run pyinstaller build.spec
# 产物：dist/mincc（macOS / Linux）或 dist/mincc.exe（Windows）

# -*- mode: python ; coding: utf-8 -*-

block_cipher = None


a = Analysis(
    ["src/mincc/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=[],
    hiddenimports=[
        # langchain 系列动态加载，PyInstaller 静态扫描容易遗漏
        "langchain",
        "langchain_core",
        "langchain_core.tools",
        "langchain_core.messages",
        "langchain_core.language_models",
        "langchain_anthropic",
        "langchain_openai",
        "langgraph",
        "langgraph.prebuilt",
        "langgraph.graph",
        # mincc 自身
        "mincc",
        "mincc.cli",
        "mincc.agent",
        "mincc.config",
        "mincc.llm",
        "mincc.prompts",
        "mincc.tools",
        "mincc.tools.read_file",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name="mincc",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
