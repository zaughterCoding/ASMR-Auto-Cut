use std::path::{Path, PathBuf};
use std::process::Command;

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

/// 跑一条后端命令，失败时把 stderr 原样带回去，前端才能显示真实原因。
fn run_backend(binary: &str, args: &[&str]) -> Result<(), String> {
    let output = backend_command(binary).args(args).output().map_err(|error| {
        format!(
            "无法执行 `{binary}`: {error}\n请把后端的 asmr-auto-cut 加入 PATH，\
             或设置环境变量 ASMR_AUTO_CUT_BIN 指向它的绝对路径。"
        )
    })?;
    if !output.status.success() {
        let stderr = String::from_utf8_lossy(&output.stderr);
        return Err(format!("`{binary} {}` 执行失败: {}", args.join(" "), stderr.trim()));
    }
    Ok(())
}

/// 分析源文件并在 `project_dir` 下落盘，返回 `project.json` 的原始 JSON 文本。
///
/// 这里刻意返回 JSON 字符串而不是在 Rust 里定义一遍结构体：时间轴的字段由
/// 后端 pydantic 模型唯一决定，前端负责解析，避免两边 schema 各写一套后漂移。
#[tauri::command]
fn analyze_source(source_path: String, project_dir: String) -> Result<String, String> {
    let binary = backend_binary();
    run_backend(
        &binary,
        &["analyze", &source_path, "--project-dir", &project_dir],
    )?;
    let project_json = PathBuf::from(&project_dir).join("project.json");
    std::fs::read_to_string(&project_json).map_err(|error| {
        format!(
            "分析已结束，但读取 {} 失败: {error}",
            project_json.display()
        )
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
fn export_project(project_path: String, output_path: String) -> Result<String, String> {
    let binary = backend_binary();
    run_backend(&binary, &["export", &project_path, "--output", &output_path])?;
    Ok(output_path)
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            analyze_source,
            load_project,
            save_project,
            export_project
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
