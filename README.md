# ASMR Auto Cut

从长时间的 ASMR 直播录像里挑出有用的内容，切掉闲聊和长时间静默，导出清理后的成片。

一场直播录下来动辄几个小时，真正想留的可能只有其中一部分，而手工在时间轴上拖拽
要花很久。这个工具先自动判断每段内容是语音、静默还是 ASMR，把结果画在原始波形上，
你在波形上逐段复核修正，然后一键导出。**全程本地处理，不上传任何东西。**

V1 是「自动判断 + 人工复核」，不是全自动——它会犯错，尤其是把耳语和轻触发声当成
说话，所以复核这一步目前不能省。

## 怎么用

```text
导入源文件 → 分析 → 在波形上复核并修正 → 保存 → 导出
```

1. **导入**：选一段录音或录像。
2. **分析**：程序抽音频、跑语音检测和静默检测，把整条录音切成若干段落，每段带一个
   标签（`asmr` / `talk` / `inactive` / `uncertain`）和一个处理方式（`keep` / `cut`）。
3. **复核**：时间轴上每一段都是可点的色块。点一段，左侧播放器跳到该段起点并开始播放，
   右侧面板可以改标签和处理方式。被标成 `cut` 的段落显示得更透明。
4. **保存**：改动写回 `segments.json`，下次打开还在。
5. **导出**：只保留标记为 `keep` 的段落，按顺序拼成一个新文件。

## 界面流程

0.2.0 的界面是**上下两层时间轴**，配一条底部的状态栏：

```text
概览层（默认整条录音，可以缩放）
    波形铺满，上面叠一个可以拖动的选区框
        ↕  框选 / 搬动选区 / 缩放，两层双向联动
缩放层（只看选区）
    选区放大后的波形 + 可点选的段落色块 + 播放头
        ↓  点一个色块 → 编辑栏里改标签和处理方式
状态栏
    分析 / 导出的进度条与当前阶段
```

**两层都能缩放，互不干扰**：上层决定「看整条录音的哪一段」，下层决定「把选中的那一段
再放大多少」。

| 操作 | 上层（概览） | 下层（缩放） |
|---|---|---|
| 普通拖动 | 框选一个范围 | — |
| 拖动已有的选区框 | 把选区搬到别处 | — |
| `Ctrl` + 滚轮 | 缩放视野 | 缩放选中的范围 |
| `Shift` + 拖动 | 平移视野 | — |
| 点一下段落色块 | 选中它 | 选中它 |
| 拖动顶部的倒三角 | — | 设置播放起点 |

概览放大后画布会描一圈淡青色边，右下角显示当前视野和总时长，点「显示整条」退回。

> **为什么上层也要能缩放**：几小时的录音放在一千多像素宽的时间轴上，一个两秒的
> 段落还不到一个像素，根本点不中。先在概览上放大到目标附近，再框选，比在整条时间轴上
> 直接拖准得多。

怎么操作：

1. **框选**：在上层波形上横向拖一段，下层的缩放视图就切到那个范围，选中区间在上层
   画成一个矩形框。
2. **搬动选区**：直接拖那个矩形框。
3. **定播放起点**：下层时间轴顶部有个倒三角，横向拖动它，播放器就跳到那个位置。
   它在播放时也会跟着走。如果播放头被缩放或平移弄出了视野，三角会贴在边上并变淡
   （表示它其实在视野之外），拖一下就能拉回来。
4. **改标签**：在下层点一个段落色块，编辑栏里用预设按钮一键改
   —— `ASMR / KEEP`、`TALK / CUT`、`INACTIVE / CUT`、`UNCERTAIN / CUT`。
5. **保存后重载**，改动还在。

换项目时视野会重置成整条；只是换选中段落不会，缩放位置会保留。

**长任务有进度**：分析和导出都会在底部状态栏显示进度条和当前阶段（比如
「正在分析音频（第 3/12 块）」），不用猜是不是卡住了。

## 支持的格式

**作为输入**（分析和导出读的源文件）：所有 ffmpeg 能解的格式都可以，包括 `.mp4`
`.mkv` `.flv` `.ts` `.mov` `.mp3` `.m4a` `.flac` `.wav` `.aac` `.ogg`。这部分不受
下面的试听限制影响。（导出文件的格式是另一回事，见[导出都做了什么](#导出都做了什么)。）

**界面内试听**用的是系统的 WebView2（Chromium 内核），它支持的容器比 ffmpeg 窄。
这条限制**只影响「听着剪」，不影响分析和导出**——放不了的封装照样能切、能导。

Windows 上实测（WebView2 Runtime 153，素材为 H.264 + AAC）：

| 扩展名 | 试听 |
|---|---|
| `.mp3` `.wav` `.flac` `.m4a` `.aac` `.ogg` / opus | ✅ |
| `.mp4` `.mov` `.mkv` | ✅（只播音轨） |
| `.flv` `.ts` | ❌ `SRC_NOT_SUPPORTED` |

放不了的话，先用 ffmpeg 转一道再导入，不影响后续流程：

```powershell
ffmpeg -i input.flv -vn -c:a aac output.m4a
```

> 试听能力取决于 WebView2 的版本，换一台机器可能不同。`.mkv` 能放是在 H.264 + AAC
> 的素材上测的，如果你的 mkv 里是 H.265 之类，未必要一样。

## 安装

需要 `ffmpeg` 和 `ffprobe` 在 PATH 上，这两个是硬性依赖，界面和命令行都要用。

### 从源码运行

```powershell
git clone <仓库地址>
cd ASMR-Auto-Cut

# 后端（虚拟环境建在仓库根目录）
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".\backend[dev]"

# 带语音检测（Silero VAD）——分析功能必需，否则只能跑命令行骨架
.\.venv\Scripts\python.exe -m pip install -e ".\backend[ml]"

# 桌面端
cd app
npm install
npm run tauri dev
```

桌面端默认按名字 `asmr-auto-cut` 从 PATH 找后端。开发时后端通常只装在项目虚拟环境里，
用环境变量指过去：

```powershell
$env:ASMR_AUTO_CUT_BIN = "<仓库路径>\.venv\Scripts\asmr-auto-cut.exe"
npm run tauri dev
```

> **`torch` 装 CUDA 版**：PyPI 上的默认是 CPU 版。要用显卡加速得从 PyTorch 官方源装：
>
> ```powershell
> .\.venv\Scripts\python.exe -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
> ```

## 命令行

不启动界面也能用，适合批处理：

```powershell
# 分析，结果写进项目目录
asmr-auto-cut analyze input.mp4 --project-dir data/projects/example

# 按时间轴导出
asmr-auto-cut export data/projects/example/segments.json --output data/projects/example/exports/clean.mp4

# 进度以 NDJSON 逐行打到 stdout，每行一条 JSON，方便被别的程序读
asmr-auto-cut analyze input.mp4 --project-dir data/projects/example --progress-json
asmr-auto-cut export data/projects/example/segments.json --output clean.mp4 --progress-json
```

`--progress-json` 下 stdout 每行一条 JSON：`{"type":"progress",...}` 是进度，
最后一条是 `{"type":"result","operation":...,"project_path":...}`。人看的进度文字
走 stderr，所以两种输出不会互相污染。

导出还有一个 `--mode`：

```powershell
asmr-auto-cut export data/projects/example/segments.json --output clean.m4a --mode fast
```

`quality`（默认）会加淡入淡出，`fast` 只跳过渐变。**说清楚：`fast` 省不了多少**——
实测 30 个保留段上 quality 1.86 秒、fast 1.76 秒，只快约 5%。原因见
[导出都做了什么](#导出都做了什么)。除非你不想要渐变，否则用默认的就好。

项目目录的内容：

```text
data/projects/example/
  project.json     源文件信息 + 时间轴
  segments.json    时间轴，界面编辑和导出都以它为准
  waveform.json    波形采样点，每秒 20 个，供界面绘制
```

抽取出来的 `analysis.wav` 只是中间产物（8 小时录音约 0.9GB），分析成功后会自动删除；
分析中途失败时会留在原地方便排查。

项目默认写在仓库根目录的 `data/projects/`，可以用环境变量 `ASMR_AUTO_CUT_DATA` 指到
别处。项目名取自源文件名，同名但源文件不同的会自动加序号，不会覆盖已有项目。

## 导出都做了什么

- 按时间轴上 `action == "keep"` 的段落切分源文件，再拼成一个。
- **音频重编码为 AAC 192k**：接缝处波形不连续会「啪」一声，所以每个保留段的音频首尾
  各加 30ms 渐变。这是音频必须重编码的唯一原因。
- **视频轨 `-c:v copy` 原样透传**，不重编码，导出速度基本只受磁盘速度限制。

代价是导出文件的时长会比「所有保留段之和」多出约 23ms——AAC 编码器的 priming 造成的，
小于一帧，可以忽略。

`--mode fast` 去掉上面那个 30ms 渐变，接缝处可能听得到爆音，换来的是……几乎没快多少。
实测 30 个保留段（每段 4 秒、带视频轨的 mp4 源）：

| 模式 | 耗时 |
|---|---|
| `quality`（默认） | 1.86 秒 |
| `fast` | 1.76 秒 |

差距这么小，是因为耗时的大头根本不是那个渐变：每一段都是一次独立的 ffmpeg 进程，
实测每次进程启动本身约 21 ms，30 段光启动就 0.64 秒；剩下的是每段各自的解码和 AAC
重编码，这两件事两种模式都要做。`fast` 目前只是「不加渐变」，**没有减少 ffmpeg 调用
次数，也没有减少临时文件**。真要缩短导出时间，得改成一次 `filter_complex` 渲染，
但那会逼着视频轨重编码，把 `-c:v copy` 的好处丢掉，所以这一版没做。

**输出容器的选择取决于源文件有没有视频轨**，两种情况不一样，实测结果：

| 扩展名 | 视频源（H.265 + AAC） | 纯音频源（AAC） |
|---|---|---|
| `.mp4` `.mkv` `.mov` | 正常，视频和音频都保留 | 正常 |
| `.m4a` | ❌ 失败 | 正常 |
| `.aac` | ⚠️ 成功，但**视频轨被丢掉**，只剩音频 | 正常 |
| `.mp3` `.flac` | ❌ 失败 | ❌ 失败 |
| `.wav` | ⚠️ 非标准的 AAC-in-WAV，很多播放器打不开 | 同左 |

原因是视频轨走 `-c:v copy` 原样透传，所以容器必须装得下源文件的视频编码。
`.m4a` 只能装音频，拿带视频轨的录像导出就会失败；反过来，源文件没有视频轨时
`.m4a` 完全没问题。同理 `.aac` 装得下音频但装不下视频，于是视频轨被静默丢掉
——它不报错，但导出的东西少了内容，这一点比失败更需要注意。

**建议**：录像导出用 `.mp4`；只想要音频时用 `.m4a`。选错了不会损坏源文件，
重新导一次即可，但目前只会抛出一段 ffmpeg 的原始报错，不太好懂。

## 打包分发

```powershell
cd app
npm run tauri build
```

Windows 上实测（首次 release 编译 1 分 41 秒；依赖都编好之后再编 1 分 10 秒）：

| 产物 | 大小 |
|---|---|
| `target/release/asmr-auto-cut.exe` | 8.8 MB |
| `bundle/msi/ASMR Auto Cut_0.2.0_x64_en-US.msi` | 2.9 MB |
| `bundle/nsis/ASMR Auto Cut_0.2.0_x64-setup.exe` | 1.9 MB |

> ⚠️ **现在打出来的安装包不能开箱即用。** 它只装了界面外壳，没有带后端，也没有带
> ffmpeg。目标机器上仍然需要自己准备：Python 3.11+、装好 `asmr-auto-cut` 后端包、
> ffmpeg 在 PATH 上。桌面端是按名字 `asmr-auto-cut` 从 PATH 找后端的，找不到就无法分析。
>
> 要让安装包能直接发给别人用，得把后端打成单文件可执行程序一起分发——这部分 V1
> 没有做，是目前最明显的缺口。

## 评估

`backend/asmr_auto_cut/evaluation/metrics.py` 可以把自动切分结果和人工标注逐帧比对，
给出两个真正关心的指标：

- `asmr_preservation_rate`——真实为 ASMR 的时间里被保住的比例（别把该留的剪掉）
- `unwanted_removal_rate`——真实为 talk/inactive 的时间里被切掉的比例（别把废话留下）

**目前只有代码接口，没有命令行入口**，要用得自己写几行 Python 调 `evaluate_segments()`。
命令行入口留到后续版本。

## 已知限制

- **仅验证过 Windows**。macOS 和 Linux 理论上能跑（Tauri 是跨平台的），但没有测过。
- **V1 会误判**。部分 ASMR 耳语和轻触发声会被当成说话，复核时手动改回即可。
- **`waveform.json` 偏大**。每秒 20 个采样点，实测每个点约 50–70 字节（浮点数字多少
  取决于音量，静音段更短），8 小时录音约 30–40MB。0.2.0 去掉了 JSON 缩进，比之前小
  约三成，但界面仍然会把它整份读进内存，长录音的响应会变慢。
- **中英混排的路径**没问题（在中文和空格路径下测过），但极长的路径未验证。

## 开发

```powershell
# 后端
cd backend
..\.venv\Scripts\python.exe -m pytest -v

# 前端（vitest）
cd app
npm test
```

改动前建议读一下 [CONTRIBUTING.md](CONTRIBUTING.md)，里面记了几个容易踩的坑。

## 许可证

[MIT](LICENSE)
