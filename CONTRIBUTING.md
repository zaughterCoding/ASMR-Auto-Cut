# 贡献指南

欢迎提 issue 和 PR。这个项目规模不大，没有太多流程要求，下面几条是实际会影响协作的部分。

## 开发环境

按 [README](README.md) 的「从源码运行」搭好即可。要点：

- 虚拟环境建在**仓库根目录**的 `.venv`，不是 `backend/` 下。
- `ffmpeg` 和 `ffprobe` 必须在 PATH 上，后端分析和导出都靠它们。
- 改动涉及 VAD 时需要装 `ml` extra（只有 `onnxruntime`）。Silero 的推理和切区间
  代码在 `analysis/silero_onnx.py`，权重在 `asmr_auto_cut/assets/`，都不依赖 torch。

## 目录结构

```text
backend/asmr_auto_cut/
  models.py        时间轴数据模型（ProjectState / TimelineSegment）
  config.py        分析参数
  media/           ffmpeg / ffprobe 封装、音频读取
  analysis/        波形、语音检测、静默检测、串起整条流水线
  timeline/        区间运算、边界微调、JSON 读写
  export/          按时间轴切分并拼接
  evaluation/      与标注结果逐帧比对算指标
  assets/          Silero 的 ONNX 权重（随包走）
app/
  src/             React 前端
  src-tauri/       Tauri 壳，负责调用后端 CLI
```

改后端时注意：`backend/` 不依赖任何界面代码，这是有意的——后端要能脱离桌面端单独跑和单独测。界面和后端之间只通过 JSON 交互，不要为了图方便让后端去适配界面内部结构。

## 跑测试

```powershell
cd backend
..\.venv\Scripts\python.exe -m pytest -v
```

`pytest` 的临时目录被固定在 `backend/.pytest_tmp`，不要改回系统临时目录。

改前端后至少跑一次类型检查和构建：

```powershell
cd app
npm run build
```

改 Rust 侧（`app/src-tauri/`）后：

```powershell
cd app\src-tauri
cargo check
```

## 提交信息

用中文写，第一行是简短的动作概述，正文说明**为什么**这么改，而不是复述改了哪几行。如果修改推翻了某个既有设计，把原因写清楚。

## 提 PR 前

- 后端测试全绿。
- 前端 `npm run build` 通过。
- 新行为有对应的测试。这个项目里「加个测试」的成本很低，请顺手加上。
- 不要提交 `docs/`、`data/`、构建产物——它们已在 `.gitignore` 里。

## 几处容易踩的坑

- **不要往系统盘写大文件。** 8 小时录音抽出来的 `analysis.wav` 约 0.9GB，所有中间产物都写在项目目录里，不要用系统临时目录。
- **桌面端调后端按名字 `asmr-auto-cut` 从 PATH 找。** 开发时用 `ASMR_AUTO_CUT_BIN` 指到 venv 里的可执行文件。
- **webview 不能直接读 `file://`。** 播放原始音频必须走 Tauri 的 asset 协议（`convertFileSrc`），不要手拼 `file://` 字符串，中文和空格路径会挂。
- **导出时视频轨是 `-c:v copy`。** 修改导出逻辑前先确认改动没有让视频重编码，这是刻意保留的行为。

## 许可证

贡献的代码按 [MIT](LICENSE) 授权。
