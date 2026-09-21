# -*- mode: python ; coding: utf-8 -*-
"""把后端冻结成一个自包含的 onedir 目录。

产物布局（装完之后就是 <安装目录>/backend/）：

    asmr-auto-cut.exe      入口
    _internal/             Python 运行时 + numpy + onnxruntime + soundfile
      asmr_auto_cut/assets/silero_vad.onnx
      onnxruntime/capi/onnxruntime.dll
      _soundfile_data/libsndfile_x64.dll

构建命令见仓库根的 README 或 app/package.json 的 freeze:backend。

**为什么是 onedir 而不是 onefile**：onefile 每次启动都要把整包解压到 %TEMP%，
而 Windows 的 %TEMP% 在 C 盘。用户的 C 盘只剩十几 G，项目里也已经两处专门
注释过「不用 %TEMP%，默认临时目录在 C 盘」（analysis/pipeline.py、
export/ffmpeg_export.py）。onedir 只解压一次，且落在安装目录里。
"""

from pathlib import Path

#: PyInstaller 在 spec 命名空间里注入 SPECPATH，即本文件所在目录。
PACKAGING_DIR = Path(SPECPATH)
BACKEND_DIR = PACKAGING_DIR.parent
PACKAGE_DIR = BACKEND_DIR / "asmr_auto_cut"

#: 生产代码的 import 图只有这几个：numpy / onnxruntime / pydantic / soundfile /
#: typer + 标准库。下面这些在 venv 里躺着但不在链条上，多半是被 hook 或
#: 包自身的 optional import 勾进来的，排除掉能省下可观的体积。
#:
#: 刻意**不排除** click / rich / pygments / colorama / shellingham：typer 真的
#: 用它们渲染 --help，排掉会改变命令行行为。
EXCLUDES = [
    # Hugging Face 整条链：本项目不用任何预训练权重下载，模型是随包的 .onnx
    "transformers",
    "tokenizers",
    "huggingface_hub",
    "hf_xet",
    "safetensors",
    # sympy 及其依赖：onnxruntime 早已把它降级成 symbolic extra
    "sympy",
    "mpmath",
    "networkx",
    # 上一轮迁移已经卸载，列在这里是防止哪天有人装回来又被打进去
    "torch",
    "torchaudio",
    "silero_vad",
    # 科学计算 / 绘图：后端一行都没用
    "matplotlib",
    "scipy",
    "pandas",
    "PIL",
    # 测试与打包工具自身
    "pytest",
    "_pytest",
    "pluggy",
    "iniconfig",
    "py",
    "pip",
    "setuptools",
    "pkg_resources",
    "_distutils_hack",
    # 交互式与 GUI
    "IPython",
    "tkinter",
    "notebook",
    "nbformat",
]

a = Analysis(
    [str(PACKAGING_DIR / "entry.py")],
    pathex=[str(BACKEND_DIR)],
    binaries=[],
    datas=[
        # PyInstaller **不会**自动收集 setuptools 的 package-data，必须显式写。
        # 落点 asmr_auto_cut/assets 正是 analysis/silero_onnx.py 里
        # importlib.resources.files("asmr_auto_cut").joinpath("assets", ...)
        # 要求的——冻结后 files() 仍返回真实的 pathlib.Path，那边一行不用改。
        (str(PACKAGE_DIR / "assets" / "silero_vad.onnx"), "asmr_auto_cut/assets"),
    ],
    # soundfile → cffi 的末端，通常能自动收到；列出来是保险。
    hiddenimports=["_cffi_backend"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="asmr-auto-cut",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    # UPX 会破坏某些 DLL，还招杀软误报，收益也不大。
    upx=False,
    # console=True 是必须的：--progress-json 走 stdout 管道，--noconsole 会让
    # Rust 侧一行都读不到。黑窗由 Rust 侧的 CREATE_NO_WINDOW 抑制，不冲突。
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    # 产物目录名：Tauri 那边按 <安装目录>/backend/ 找入口 exe。
    name="backend",
)
