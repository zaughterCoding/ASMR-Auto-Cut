use std::io::{BufRead, BufReader, Read};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::thread;

use tauri::{AppHandle, Emitter};

/// 后端 CLI 的可执行文件名。
///
/// 默认从 PATH 查找 `asmr-auto-cut`；开发环境下它通常只装在项目 venv 的
/// Scripts 目录里、并没有进 PATH，这时用 `ASMR_AUTO_CUT_BIN` 指过去即可。
fn backend_binary() -> String {
    std::env::var("ASMR_AUTO_CUT_BIN").unwrap_or_else(|_| "asmr-auto-cut".to_string())
}

fn backend_command(binary: &str) -> Command {
    let mut command = Command::new(binary);
    // GUI 进程调起控制台子进程时，Windows 会弹一个黑窗，这里抑制掉。
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    command
}

/// 启动一条带 `--progress-json` 的后端命令，逐行读 stdout：`progress` 记录转成
/// Tauri 事件发给前端，`result` 记录留作返回值。失败时把 stderr 原样带回去。
///
/// 不能用 `Command::output()`：那个要等进程结束才返回，中间几个小时的导出过程中
/// 前端拿不到任何东西，进度条就只能干等着。
///
/// 返回 `Option<Value>`：`result` 记录是给调用方的，但有些命令不产生它，所以是
/// Option 而不是直接报错。
fn run_backend_with_progress(
    app: &AppHandle,
    binary: &str,
    args: &[&str],
) -> Result<Option<serde_json::Value>, String> {
    let mut child = backend_command(binary)
        .args(args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .map_err(|error| {
            format!(
                "无法执行 `{binary}`: {error}\n请把后端的 asmr-auto-cut 加入 PATH，\
                 或设置环境变量 ASMR_AUTO_CUT_BIN 指向它的绝对路径。"
            )
        })?;

    let stdout = child.stdout.take().ok_or("无法读取后端 stdout")?;

    // stderr 必须另开一条线程同时读掉。管道缓冲区只有 64KB：这里正逐行读 stdout，
    // 子进程一旦往 stderr 写满缓冲区就会阻塞，它一阻塞就不再产生 stdout，这边读不到
    // 行也就走不到下面的 wait —— 双方互等，应用卡死且不给任何提示。
    // 失败时 stderr 里装的正是真正的报错，恰恰是最需要看到它的时候。
    // 实测正常导出 stderr 是 0 字节、报错时几 KB，离 64KB 还远，所以这条目前是
    // 防御性的：挡的是以后某个依赖开始往 stderr 大量输出。
    let stderr = child.stderr.take().ok_or("无法读取后端 stderr")?;
    let stderr_reader = thread::spawn(move || {
        let mut bytes = Vec::new();
        let _ = BufReader::new(stderr).read_to_end(&mut bytes);
        // 后端在 --progress-json 下会把 stderr 也固定成 UTF-8，但这里仍然用
        // lossy：万一有别的进程往里写，宁可看到替换字符也不能丢报错。
        String::from_utf8_lossy(&bytes).into_owned()
    });

    let mut result_event: Option<serde_json::Value> = None;
    for line in BufReader::new(stdout).lines() {
        // lines() 会把行尾的 \n 和 CRLF 的 \r 一起去掉。后端在 Windows 上按文本
        // 模式写 stdout，行尾确实是 \r\n，不处理的话每行尾部都会多一个 \r，
        // 解析 JSON 时虽然能过，但把内容拿去比较就会莫名其妙地不相等。
        let line = line.map_err(|error| format!("读取后端进度失败: {error}"))?;
        if line.trim().is_empty() {
            continue;
        }
        let value: serde_json::Value = serde_json::from_str(&line)
            .map_err(|error| format!("后端输出不是 JSON: {line}\n{error}"))?;
        match value.get("type").and_then(|item| item.as_str()) {
            Some("progress") => {
                app.emit("backend-progress", value)
                    .map_err(|error| format!("发送进度事件失败: {error}"))?;
            }
            Some("result") => result_event = Some(value),
            _ => {}
        }
    }

    let status = child
        .wait()
        .map_err(|error| format!("等待后端命令失败: {error}"))?;
    let stderr = stderr_reader.join().unwrap_or_default();
    if !status.success() {
        return Err(format!(
            "`{binary} {}` 执行失败: {}",
            args.join(" "),
            stderr.trim()
        ));
    }
    Ok(result_event)
}

/// 分析源文件并在 `project_dir` 下落盘，返回 `project.json` 的原始 JSON 文本。
///
/// 这里刻意返回 JSON 字符串而不是在 Rust 里定义一遍结构体：时间轴的字段由
/// 后端 pydantic 模型唯一决定，前端负责解析，避免两边 schema 各写一套后漂移。
#[tauri::command]
fn analyze_source(
    app: AppHandle,
    source_path: String,
    project_dir: String,
    review: String,
) -> Result<String, String> {
    let binary = backend_binary();
    run_backend_with_progress(
        &app,
        &binary,
        &[
            "analyze",
            &source_path,
            "--project-dir",
            &project_dir,
            // 复核细致程度：决定多宽的「拿不准」会被标出来给人听。取值由后端校验，
            // 前端只是把人选的那一档原样转发，档位定义以后端 config.REVIEW_BANDS 为准。
            "--review",
            &review,
            "--progress-json",
        ],
    )?;
    let project_json = PathBuf::from(&project_dir).join("project.json");
    std::fs::read_to_string(&project_json).map_err(|error| {
        format!(
            "分析已结束，但读取 {} 失败: {error}",
            project_json.display()
        )
    })
}

/// 项目数据的根目录，即设计文档 §14 的 `data/projects/`。
///
/// 前端拿不到仓库位置，只能由后端推。从当前目录往上找到同时含 `backend/` 和
/// `app/` 的一层当作仓库根；`tauri dev` 的工作目录是 `app/src-tauri`，正好能命中。
/// 找不到就退回到当前目录下的 `data/projects`，至少不会是错的相对路径。
/// 用运行时查找而不是编译期常量，避免把开发机的绝对路径烧进二进制。
fn projects_root() -> PathBuf {
    if let Ok(configured) = std::env::var("ASMR_AUTO_CUT_DATA") {
        return PathBuf::from(configured);
    }
    let current = std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."));
    for candidate in current.ancestors() {
        if candidate.join("backend").is_dir() && candidate.join("app").is_dir() {
            return candidate.join("data").join("projects");
        }
    }
    current.join("data").join("projects")
}

#[tauri::command]
fn projects_root_path() -> String {
    let root = projects_root();
    // 让目录先存在，前端才好把它展示出来或往里放东西
    let _ = std::fs::create_dir_all(&root);
    root.to_string_lossy().to_string()
}

/// 读取项目目录下的 waveform.json 原始 JSON 文本。波形点数随录音时长增长，
/// 前端按像素列聚合后再绘制，不逐点画。
#[tauri::command]
fn load_waveform(project_dir: String) -> Result<String, String> {
    let waveform_json = PathBuf::from(&project_dir).join("waveform.json");
    std::fs::read_to_string(&waveform_json).map_err(|error| {
        format!("读取 {} 失败: {error}", waveform_json.display())
    })
}

#[tauri::command]
fn load_project(project_path: String) -> Result<String, String> {
    std::fs::read_to_string(&project_path)
        .map_err(|error| format!("读取 {project_path} 失败: {error}"))
}

#[tauri::command]
fn save_project(project_path: String, state_json: String) -> Result<(), String> {
    if let Some(parent) = Path::new(&project_path).parent() {
        std::fs::create_dir_all(parent)
            .map_err(|error| format!("创建 {} 失败: {error}", parent.display()))?;
    }
    std::fs::write(&project_path, state_json)
        .map_err(|error| format!("写入 {project_path} 失败: {error}"))
}

#[tauri::command]
fn export_project(
    app: AppHandle,
    project_path: String,
    output_path: String,
) -> Result<String, String> {
    let binary = backend_binary();
    run_backend_with_progress(
        &app,
        &binary,
        &[
            "export",
            &project_path,
            "--output",
            &output_path,
            "--progress-json",
        ],
    )?;
    Ok(output_path)
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![
            analyze_source,
            load_waveform,
            load_project,
            save_project,
            export_project,
            projects_root_path
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
