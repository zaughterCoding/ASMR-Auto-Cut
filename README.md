# ASMR Auto Cut

从长时间的 ASMR 直播录像里挑出有用的内容，切掉废话和长时间静默，导出清理后的成片。

V1 用 Silero VAD 检测语音、用能量规则检测长时间低活动段，把结果标在原始波形上，
由你逐段复核修正后再导出。所有处理都在本地完成。

## 组成

- `backend/` —— 处理核心。FFmpeg 抽音频、Silero VAD 检测语音、规则检测静默，
  产出稳定的 JSON 中间格式。可以脱离界面单独用命令行跑。
- `app/` —— Tauri 桌面壳 + React 前端。读上面那套 JSON，画波形、改时间轴、导出。

界面和后端之间只通过 JSON 通信，不耦合模型内部结构，所以后端可以独立测试、批处理。

## 环境要求

- Python 3.11+
- Node.js 18+
- `ffmpeg` 与 `ffprobe` 在 PATH 上
- Rust 工具链（只构建桌面端时需要）

## 后端

在本仓库根目录建虚拟环境并安装：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".\backend[dev]"
```

带机器学习部分（Silero VAD）时再装：

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".\backend[ml]"
```

> `torch` 的 CUDA 版本要从 PyTorch 官方源单独装，PyPI 上的默认是 CPU 版：
>
> ```powershell
> .\.venv\Scripts\python.exe -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
> ```
>
> `silero-vad` 6.x 的 `__init__.py` 会无条件 import `sequence_vad`，后者依赖
> `onnxruntime`，但 `onnxruntime` 只声明在 `onnx-cpu` / `onnx-gpu` 两个 extra 里。
> 所以 `pyproject.toml` 里写的是 `silero-vad[onnx-cpu]`，不带上这个 extra 连
> `import silero_vad` 都会失败。

确认可执行：

```powershell
.\.venv\Scripts\asmr-auto-cut.exe --version
```

### 分析

```powershell
asmr-auto-cut analyze input.mp4 --project-dir data/projects/example
```

产物落在项目目录下：

```text
data/projects/example/
  project.json     分析结果（源文件信息 + 时间轴）
  segments.json    时间轴，界面编辑和导出都以它为准
  waveform.json    波形采样点，每秒 20 个，供界面绘制
```

抽取出来的 `analysis.wav` 只是 VAD 和波形计算的中间产物，分析成功后会自动删除
（整条录音的体积可观，8 小时约 0.9GB）。分析中途失败时会留在原地便于排查。

### 导出

```powershell
asmr-auto-cut export data/projects/example/segments.json --output data/projects/example/exports/clean.mp4
```

按时间轴上 `action == "keep"` 的段落切分源文件再拼接。

接缝处波形不连续会产生爆音，所以每个保留段的音频首尾各加 30ms 渐变，
音频因此重编码为 AAC 192k；视频轨用 `-c:v copy` 原样透传，不重编码。

## 桌面端

```powershell
cd app
npm install
npm run tauri dev
```

界面上的操作：导入源文件 → 分析 → 在波形上点选片段并修正标签/处理方式 → 保存 → 导出。

项目数据默认写在仓库根目录的 `data/projects/`，可用环境变量 `ASMR_AUTO_CUT_DATA`
指到别处。项目名取自源文件名；同名但源文件不同的会自动加序号，不会覆盖已有项目。

桌面端按名称 `asmr-auto-cut` 从 PATH 找后端。开发时它通常只在项目 venv 里，
用环境变量指过去：

```powershell
$env:ASMR_AUTO_CUT_BIN = "E:\path\to\ASMR-Auto-Cut\.venv\Scripts\asmr-auto-cut.exe"
```

## 评估

`backend/asmr_auto_cut/evaluation/metrics.py` 把两份时间轴逐帧比对，给出
`asmr_preservation_rate`（真实为 ASMR 的时间里被保住的比例）与
`unwanted_removal_rate`（真实为 talk/inactive 的时间里被切掉的比例）——
这两个才是这个工具真正关心的：别把 ASMR 剪掉，也别把废话留下。

## 测试

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -v
```

> `pyproject.toml` 里把 pytest 的临时目录设成了项目内的 `.pytest_tmp`，
> 避免落到系统盘的临时目录。

## 已知限制

- WebView2 支持的容器有限，`.mkv` / `.flv` 这类直播常见封装可能无法在界面里试听，
  但分析和导出不受影响。
- V1 会把部分 ASMR 耳语和轻触发声误判成语音，复核时手动改回即可。
- 桌面端只在 Windows 上验证过。
