use base64::{engine::general_purpose::STANDARD as BASE64, Engine};
use quick_xml::events::Event;
use quick_xml::Reader;
use serde::{Deserialize, Serialize};
use std::fs;
use std::io::{BufReader, Read};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::{Arc, Mutex, OnceLock};
use std::thread;
use tauri::{AppHandle, Emitter};

/// GUI/LaunchServices 启动时通常没有有效 UTF-8 locale，Subversion 会把非 ASCII
/// 路径转成 `{U+XXXX}` 形式。强制给 svn 子进程设置 UTF-8 区域设置，并在解析时
/// 兼容解码这类转义，确保中文文件名正常显示。
fn apply_svn_locale(cmd: &mut Command) {
    // C.UTF-8 / en_US.UTF-8 在 macOS 均可用；优先 C.UTF-8，行为更接近无翻译的 C。
    const LANG: &str = "C.UTF-8";
    cmd.env("LANG", LANG);
    cmd.env("LC_ALL", LANG);
    cmd.env("LC_CTYPE", LANG);
    cmd.env("LC_MESSAGES", LANG);
}

fn decode_svn_unicode_escapes(input: &str) -> String {
    // svn 在非 UTF-8 locale 下会输出: {U+4F1A}{U+5458}...
    if !input.contains("{U+") {
        return input.to_string();
    }
    let bytes = input.as_bytes();
    let mut out = String::with_capacity(input.len());
    let mut i = 0;
    while i < bytes.len() {
        if bytes[i] == b'{' && i + 3 < bytes.len() && bytes[i + 1] == b'U' && bytes[i + 2] == b'+' {
            let mut j = i + 3;
            while j < bytes.len() && bytes[j].is_ascii_hexdigit() {
                j += 1;
            }
            if j > i + 3 && j < bytes.len() && bytes[j] == b'}' {
                if let Ok(hex) = std::str::from_utf8(&bytes[i + 3..j]) {
                    if let Ok(code) = u32::from_str_radix(hex, 16) {
                        if let Some(ch) = char::from_u32(code) {
                            out.push(ch);
                            i = j + 1;
                            continue;
                        }
                    }
                }
            }
        }
        // 普通字符按 UTF-8 边界推进
        let ch = input[i..].chars().next().unwrap();
        out.push(ch);
        i += ch.len_utf8();
    }
    out
}

fn normalize_svn_text(input: &str) -> String {
    decode_svn_unicode_escapes(input)
}

fn svn_binary() -> &'static str {
    static SVN_BIN: OnceLock<String> = OnceLock::new();
    SVN_BIN
        .get_or_init(|| {
            // GUI/Tauri 启动时 PATH 通常不含 Homebrew，优先探测绝对路径
            let candidates = [
                "/opt/homebrew/bin/svn",
                "/usr/local/bin/svn",
                "/opt/local/bin/svn",
                "/usr/bin/svn",
                "svn",
            ];

            for candidate in candidates {
                // 绝对路径先确认文件存在，避免误报 No such file
                if candidate.starts_with('/') && !Path::new(candidate).exists() {
                    continue;
                }
                let mut cmd = Command::new(candidate);
                cmd.arg("--version").arg("--quiet");
                if cmd.output().map(|o| o.status.success()).unwrap_or(false) {
                    return candidate.to_string();
                }
            }

            // 兜底：通过 login shell 读取用户 PATH 后再找
            if let Ok(output) = Command::new("/bin/zsh")
                .args(["-lc", "command -v svn || true"])
                .output()
            {
                if output.status.success() {
                    let found = String::from_utf8_lossy(&output.stdout).trim().to_string();
                    if !found.is_empty() && Path::new(&found).exists() {
                        return found;
                    }
                }
            }

            // 再尝试 bash login
            if let Ok(output) = Command::new("/bin/bash")
                .args(["-lc", "command -v svn || true"])
                .output()
            {
                if output.status.success() {
                    let found = String::from_utf8_lossy(&output.stdout).trim().to_string();
                    if !found.is_empty() && Path::new(&found).exists() {
                        return found;
                    }
                }
            }

            "/opt/homebrew/bin/svn".to_string()
        })
        .as_str()
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct FsEntry {
    pub name: String,
    pub path: String,
    pub is_dir: bool,
    pub size: u64,
    pub modified: Option<u64>,
    pub extension: Option<String>,
    pub svn_status: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CommandResult {
    pub success: bool,
    pub stdout: String,
    pub stderr: String,
    pub code: Option<i32>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SvnProgressEvent {
    pub job_id: String,
    pub phase: String,
    pub line: Option<String>,
    pub stream: Option<String>,
    pub success: Option<bool>,
    pub code: Option<i32>,
    pub message: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PreviewPayload {
    pub kind: String,
    pub path: String,
    pub name: String,
    pub size: u64,
    pub mime: Option<String>,
    pub content: Option<String>,
    pub data_url: Option<String>,
    pub message: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SvnStatusItem {
    pub path: String,
    pub name: String,
    pub status: String,
    pub is_dir: bool,
    pub relative_path: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SvnLogPath {
    pub path: String,
    pub action: String,
    pub kind: Option<String>,
    pub copy_from_path: Option<String>,
    pub copy_from_revision: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SvnLogEntry {
    pub revision: String,
    pub author: Option<String>,
    pub date: Option<String>,
    pub message: String,
    pub paths: Vec<SvnLogPath>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DiffFileInfo {
    pub path: String,
    pub relative_path: String,
    pub name: String,
    pub status: String,
    pub status_label: String,
    pub binary: bool,
    pub is_dir: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct DiffFileContent {
    pub path: String,
    pub relative_path: String,
    pub name: String,
    pub status: String,
    pub status_label: String,
    pub binary: bool,
    pub old_text: String,
    pub new_text: String,
    pub old_exists: bool,
    pub new_exists: bool,
    pub language: String,
    pub message: Option<String>,
}

fn run_svn(args: &[&str], cwd: Option<&Path>) -> Result<CommandResult, String> {
    let svn = svn_binary();
    let mut cmd = Command::new(svn);
    cmd.args(args);
    apply_svn_locale(&mut cmd);
    if let Some(dir) = cwd {
        cmd.current_dir(dir);
    }

    let output = cmd.output().map_err(|e| {
        format!(
            "无法执行 svn 命令（当前解析路径: {svn}）。请确认已安装 Subversion，例如: brew install svn。原始错误: {e}"
        )
    })?;

    let stdout = normalize_svn_text(&String::from_utf8_lossy(&output.stdout));
    let stderr = normalize_svn_text(&String::from_utf8_lossy(&output.stderr));
    let code = output.status.code();
    let success = output.status.success();

    if !success && stdout.trim().is_empty() && !stderr.trim().is_empty() {
        return Err(stderr.trim().to_string());
    }

    Ok(CommandResult {
        success,
        stdout,
        stderr,
        code,
    })
}

fn emit_progress(app: &AppHandle, event: SvnProgressEvent) {
    let _ = app.emit("svn-progress", event);
}

fn sanitize_log_line(line: &str) -> String {
    normalize_svn_text(line)
        .chars()
        .filter(|c| {
            let u = *c as u32;
            // 保留常见空白，去掉控制符（含 EOT/^D、BEL 等）
            *c == '\t' || *c == '\n' || u >= 0x20
        })
        .collect::<String>()
        .trim_end_matches(['\r', ' '])
        .to_string()
}

/// 供异步任务在失败兜底时推送错误结束事件（幂等：前端收到后结束进度窗）。
pub fn emit_job_error(app: &AppHandle, job_id: &str, message: &str) {
    emit_progress(
        app,
        SvnProgressEvent {
            job_id: job_id.to_string(),
            phase: "error".into(),
            line: Some(message.to_string()),
            stream: Some("stderr".into()),
            success: Some(false),
            code: None,
            message: Some(message.to_string()),
        },
    );
}

pub fn emit_job_done(app: &AppHandle, job_id: &str, success: bool, message: &str) {
    emit_progress(
        app,
        SvnProgressEvent {
            job_id: job_id.to_string(),
            phase: if success {
                "done".into()
            } else {
                "error".into()
            },
            line: if success {
                None
            } else {
                Some(message.to_string())
            },
            stream: if success { None } else { Some("stderr".into()) },
            success: Some(success),
            code: None,
            message: Some(message.to_string()),
        },
    );
}

/// 逐字节读管道并按行推送，避免整段缓冲到结束才显示。
fn pump_lines<R: std::io::Read + Send + 'static>(
    reader: R,
    app: AppHandle,
    job_id: String,
    stream: &'static str,
    collect: Arc<Mutex<String>>,
) -> thread::JoinHandle<()> {
    thread::spawn(move || {
        let mut reader = BufReader::new(reader);
        let mut line_buf: Vec<u8> = Vec::with_capacity(512);
        let mut byte = [0u8; 1];
        loop {
            match reader.read(&mut byte) {
                Ok(0) => break,
                Ok(_) => {
                    let b = byte[0];
                    if b == b'\n' {
                        let line = sanitize_log_line(
                            &String::from_utf8_lossy(&line_buf).trim_end_matches('\r'),
                        );
                        line_buf.clear();
                        if line.is_empty() {
                            continue;
                        }
                        if let Ok(mut buf) = collect.lock() {
                            if !buf.is_empty() {
                                buf.push('\n');
                            }
                            buf.push_str(&line);
                        }
                        emit_progress(
                            &app,
                            SvnProgressEvent {
                                job_id: job_id.clone(),
                                phase: "log".into(),
                                line: Some(line),
                                stream: Some(stream.into()),
                                success: None,
                                code: None,
                                message: None,
                            },
                        );
                    } else if b != b'\r' {
                        line_buf.push(b);
                    }
                }
                Err(_) => break,
            }
        }

        if !line_buf.is_empty() {
            let line =
                sanitize_log_line(&String::from_utf8_lossy(&line_buf).trim_end_matches('\r'));
            if !line.is_empty() {
                if let Ok(mut buf) = collect.lock() {
                    if !buf.is_empty() {
                        buf.push('\n');
                    }
                    buf.push_str(&line);
                }
                emit_progress(
                    &app,
                    SvnProgressEvent {
                        job_id,
                        phase: "log".into(),
                        line: Some(line),
                        stream: Some(stream.into()),
                        success: None,
                        code: None,
                        message: None,
                    },
                );
            }
        }
    })
}

fn run_svn_streaming(
    app: &AppHandle,
    job_id: &str,
    args: &[&str],
    cwd: Option<&Path>,
    title: &str,
    notify_done: bool,
) -> Result<CommandResult, String> {
    let svn = svn_binary();
    emit_progress(
        app,
        SvnProgressEvent {
            job_id: job_id.to_string(),
            phase: "start".into(),
            line: None,
            stream: None,
            success: None,
            code: None,
            message: Some(format!("{title}\n$ {svn} {}", args.join(" "))),
        },
    );

    // macOS 的 script 会分配伪终端，迫使 svn 按行刷新进度，而不是整段缓冲到结束。
    let use_script = Path::new("/usr/bin/script").exists();
    let mut cmd = if use_script {
        let mut c = Command::new("/usr/bin/script");
        c.arg("-q").arg("/dev/null").arg(svn);
        c.args(args);
        c
    } else {
        let mut c = Command::new(svn);
        c.args(args);
        c
    };

    if let Some(dir) = cwd {
        cmd.current_dir(dir);
    }
    // 尽量关闭环境层额外缓冲
    cmd.env("PYTHONUNBUFFERED", "1");
    apply_svn_locale(&mut cmd);
    cmd.stdout(Stdio::piped()).stderr(Stdio::piped());

    let mut child = cmd.spawn().map_err(|e| {
        let msg = format!(
            "无法执行 svn 命令（当前解析路径: {svn}）。请确认已安装 Subversion，例如: brew install svn。原始错误: {e}"
        );
        emit_progress(
            app,
            SvnProgressEvent {
                job_id: job_id.to_string(),
                phase: "error".into(),
                line: Some(msg.clone()),
                stream: Some("stderr".into()),
                success: Some(false),
                code: None,
                message: Some(msg.clone()),
            },
        );
        msg
    })?;

    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "无法捕获 svn 标准输出".to_string())?;
    let stderr = child
        .stderr
        .take()
        .ok_or_else(|| "无法捕获 svn 标准错误".to_string())?;

    let stdout_buf = Arc::new(Mutex::new(String::new()));
    let stderr_buf = Arc::new(Mutex::new(String::new()));

    let t_out = pump_lines(
        stdout,
        app.clone(),
        job_id.to_string(),
        "stdout",
        Arc::clone(&stdout_buf),
    );
    let t_err = pump_lines(
        stderr,
        app.clone(),
        job_id.to_string(),
        "stderr",
        Arc::clone(&stderr_buf),
    );

    let status = child
        .wait()
        .map_err(|e| format!("等待 svn 进程结束失败: {e}"))?;
    let _ = t_out.join();
    let _ = t_err.join();

    let stdout_text = stdout_buf.lock().map(|g| g.clone()).unwrap_or_default();
    let stderr_text = stderr_buf.lock().map(|g| g.clone()).unwrap_or_default();
    let code = status.code();
    // script 包装时退出码仍来自子进程；success 以 status 为准
    let success = status.success();

    if !success && stdout_text.trim().is_empty() && !stderr_text.trim().is_empty() {
        let msg = stderr_text.trim().to_string();
        if notify_done {
            emit_progress(
                app,
                SvnProgressEvent {
                    job_id: job_id.to_string(),
                    phase: "error".into(),
                    line: Some(msg.clone()),
                    stream: Some("stderr".into()),
                    success: Some(false),
                    code,
                    message: Some(msg.clone()),
                },
            );
        }
        return Err(msg);
    }

    if notify_done {
        emit_progress(
            app,
            SvnProgressEvent {
                job_id: job_id.to_string(),
                phase: "done".into(),
                line: None,
                stream: None,
                success: Some(success),
                code,
                message: Some(if success {
                    "操作完成".into()
                } else {
                    "操作结束（存在错误或警告）".into()
                }),
            },
        );
    }

    Ok(CommandResult {
        success,
        stdout: stdout_text,
        stderr: stderr_text,
        code,
    })
}

fn ensure_path_exists(path: &str) -> Result<PathBuf, String> {
    let p = PathBuf::from(path);
    if !p.exists() {
        return Err(format!("路径不存在: {path}"));
    }
    Ok(p)
}

fn extension_of(path: &Path) -> Option<String> {
    path.extension()
        .and_then(|e| e.to_str())
        .map(|s| s.to_lowercase())
}

fn guess_mime(ext: &str) -> &'static str {
    match ext {
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "gif" => "image/gif",
        "webp" => "image/webp",
        "svg" => "image/svg+xml",
        "bmp" => "image/bmp",
        "ico" => "image/x-icon",
        "pdf" => "application/pdf",
        "json" => "application/json",
        "xml" => "application/xml",
        "html" | "htm" => "text/html",
        "css" => "text/css",
        "js" | "mjs" | "cjs" => "text/javascript",
        "ts" | "tsx" => "text/typescript",
        "md" | "markdown" => "text/markdown",
        "txt" | "log" | "ini" | "conf" | "cfg" | "yml" | "yaml" | "toml" | "csv" => "text/plain",
        "rs" | "java" | "kt" | "go" | "py" | "rb" | "php" | "c" | "cpp" | "h" | "hpp" | "cs"
        | "swift" | "sh" | "bash" | "zsh" | "sql" | "vue" | "jsx" => "text/plain",
        _ => "application/octet-stream",
    }
}

fn is_text_ext(ext: &str) -> bool {
    matches!(
        ext,
        "txt"
            | "md"
            | "markdown"
            | "json"
            | "xml"
            | "yml"
            | "yaml"
            | "toml"
            | "ini"
            | "conf"
            | "cfg"
            | "log"
            | "csv"
            | "html"
            | "htm"
            | "css"
            | "js"
            | "mjs"
            | "cjs"
            | "ts"
            | "tsx"
            | "jsx"
            | "vue"
            | "rs"
            | "java"
            | "kt"
            | "go"
            | "py"
            | "rb"
            | "php"
            | "c"
            | "cpp"
            | "h"
            | "hpp"
            | "cs"
            | "swift"
            | "sh"
            | "bash"
            | "zsh"
            | "sql"
            | "gitignore"
            | "env"
            | "properties"
            | "gradle"
            | "plist"
            | "svg"
    )
}

fn is_image_ext(ext: &str) -> bool {
    matches!(
        ext,
        "png" | "jpg" | "jpeg" | "gif" | "webp" | "bmp" | "ico" | "svg"
    )
}

fn looks_like_text(bytes: &[u8]) -> bool {
    if bytes.is_empty() {
        return true;
    }
    let sample = &bytes[..bytes.len().min(4096)];
    let mut weird = 0usize;
    for b in sample {
        if *b == 0 {
            return false;
        }
        if *b < 0x09 {
            weird += 1;
        }
    }
    (weird as f64 / sample.len() as f64) < 0.05
}

fn parse_status_map(stdout: &str) -> std::collections::HashMap<String, String> {
    let mut map = std::collections::HashMap::new();
    for line in stdout.lines() {
        let line = line.trim_end();
        if line.is_empty() {
            continue;
        }
        // svn status uses fixed first 8 columns, then path.
        // Use char-based slicing so non-ASCII paths do not break.
        let chars: Vec<char> = line.chars().collect();
        if chars.len() < 9 {
            continue;
        }
        let code = chars[0];
        if code == ' ' || code == '\t' {
            continue;
        }
        let path_part: String =
            normalize_svn_text(&chars[8..].iter().collect::<String>().trim().to_string());
        if path_part.is_empty() {
            continue;
        }
        // Prefer bare file/dir name for matching current directory listing.
        let name = Path::new(&path_part)
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or(path_part.as_str())
            .to_string();
        map.insert(name, code.to_string());
    }
    map
}

pub fn list_directory(path: String) -> Result<Vec<FsEntry>, String> {
    let dir = ensure_path_exists(&path)?;
    if !dir.is_dir() {
        return Err("目标不是文件夹".into());
    }

    let status_map = run_svn(&["status", "--depth=immediates"], Some(&dir))
        .map(|r| parse_status_map(&r.stdout))
        .unwrap_or_default();

    let mut entries = Vec::new();
    let read = fs::read_dir(&dir).map_err(|e| format!("读取目录失败: {e}"))?;
    for item in read {
        let item = item.map_err(|e| format!("读取目录项失败: {e}"))?;
        let meta = item
            .metadata()
            .map_err(|e| format!("读取元数据失败: {e}"))?;
        let name = item.file_name().to_string_lossy().to_string();
        if name == ".svn" {
            continue;
        }
        let full = item.path();
        let modified = meta
            .modified()
            .ok()
            .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
            .map(|d| d.as_secs());
        let svn_status = status_map.get(&name).cloned();
        entries.push(FsEntry {
            name: name.clone(),
            path: full.to_string_lossy().to_string(),
            is_dir: meta.is_dir(),
            size: if meta.is_file() { meta.len() } else { 0 },
            modified,
            extension: extension_of(&full),
            svn_status,
        });
    }

    entries.sort_by(|a, b| match (a.is_dir, b.is_dir) {
        (true, false) => std::cmp::Ordering::Less,
        (false, true) => std::cmp::Ordering::Greater,
        _ => a.name.to_lowercase().cmp(&b.name.to_lowercase()),
    });

    Ok(entries)
}

pub fn checkout(
    app: &AppHandle,
    job_id: &str,
    url: String,
    path: String,
) -> Result<CommandResult, String> {
    let target = PathBuf::from(&path);
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("创建父目录失败: {e}"))?;
    }
    run_svn_streaming(
        app,
        job_id,
        &["checkout", &url, &path],
        None,
        "正在检出工作副本...",
        false, // 由上层在写入工作区列表后发送 done，避免竞态
    )
}

pub fn update(app: &AppHandle, job_id: &str, path: String) -> Result<CommandResult, String> {
    let p = ensure_path_exists(&path)?;
    run_svn_streaming(
        app,
        job_id,
        &["update", p.to_str().unwrap_or(&path)],
        None,
        "正在更新...",
        true,
    )
}

pub fn commit(
    path: String,
    message: String,
    paths: Option<Vec<String>>,
) -> Result<CommandResult, String> {
    let p = ensure_path_exists(&path)?;
    let msg = message.trim();
    if msg.is_empty() {
        return Err("提交说明不能为空".into());
    }

    let selected: Vec<String> = paths
        .unwrap_or_default()
        .into_iter()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
        .collect();

    if selected.is_empty() {
        // 兼容：未指定路径时，对目标路径提交（不再自动 add 全部）
        return run_svn(&["commit", "-m", msg, p.to_str().unwrap_or(&path)], None);
    }

    // 先把未版本控制项 add 进去
    for item in &selected {
        if let Ok(status) = status_of(item) {
            if status.as_deref() == Some("?") {
                let _ = add_paths(vec![item.clone()]);
            }
        }
    }

    // 提交时使用目标路径的父目录/目录作为 cwd，路径参数用绝对路径更稳妥
    let cwd = if p.is_dir() {
        p.clone()
    } else {
        p.parent().unwrap_or(p.as_path()).to_path_buf()
    };
    let mut args: Vec<String> = vec!["commit".into(), "-m".into(), msg.to_string()];
    args.extend(selected);
    let arg_refs: Vec<&str> = args.iter().map(|s| s.as_str()).collect();
    run_svn(&arg_refs, Some(&cwd))
}

fn status_of(path: &str) -> Result<Option<String>, String> {
    let p = PathBuf::from(path);
    let parent = p
        .parent()
        .map(|x| x.to_path_buf())
        .unwrap_or_else(|| PathBuf::from("."));
    let name = p
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or(path)
        .to_string();
    let res = run_svn(&["status", "--depth=empty", &name], Some(&parent))?;
    for line in res.stdout.lines() {
        let chars: Vec<char> = line.chars().collect();
        if chars.is_empty() {
            continue;
        }
        let code = chars[0];
        if code == ' ' {
            continue;
        }
        return Ok(Some(code.to_string()));
    }
    Ok(None)
}

/// 解析 svn status 输出。cwd 用于把相对路径还原为绝对路径。
fn parse_status_items(stdout: &str, cwd: &Path) -> Vec<SvnStatusItem> {
    let mut items = Vec::new();
    for line in stdout.lines() {
        let line = line.trim_end();
        if line.is_empty() {
            continue;
        }
        let chars: Vec<char> = line.chars().collect();
        if chars.len() < 9 {
            continue;
        }
        let code = chars[0];
        // property-only 变更（第一列为空白，第二列有标记）
        if code == ' ' {
            let prop = chars.get(1).copied().unwrap_or(' ');
            if prop == ' ' {
                continue;
            }
        }
        let path_part: String =
            normalize_svn_text(&chars[8..].iter().collect::<String>().trim().to_string());
        if path_part.is_empty() {
            continue;
        }
        // 跳过状态汇总类行
        if path_part.starts_with("Performing status") {
            continue;
        }
        let full = {
            let candidate = PathBuf::from(&path_part);
            if candidate.is_absolute() {
                candidate
            } else {
                cwd.join(&path_part)
            }
        };
        let full_str = full.to_string_lossy().to_string();
        let name = full
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or(path_part.as_str())
            .to_string();
        let is_dir = full.is_dir();
        let relative = full
            .strip_prefix(cwd)
            .map(|r| r.to_string_lossy().to_string())
            .unwrap_or_else(|_| path_part.clone());
        let status = if code == ' ' {
            chars
                .get(1)
                .map(|c| c.to_string())
                .unwrap_or_else(|| "M".into())
        } else {
            code.to_string()
        };
        items.push(SvnStatusItem {
            path: full_str,
            name,
            status,
            is_dir,
            relative_path: relative,
        });
    }
    items
}

fn path_file_name(path: &Path) -> String {
    path.file_name()
        .and_then(|s| s.to_str())
        .unwrap_or_else(|| path.to_str().unwrap_or("."))
        .to_string()
}

fn sort_status_items(items: &mut [SvnStatusItem]) {
    items.sort_by(|a, b| {
        a.relative_path
            .to_lowercase()
            .cmp(&b.relative_path.to_lowercase())
    });
}

fn is_same_or_child_path(child: &str, parent: &str) -> bool {
    if child == parent {
        return true;
    }
    let child_n = child.replace('\\', "/");
    let parent_n = parent.replace('\\', "/").trim_end_matches('/').to_string();
    child_n.starts_with(&(parent_n + "/"))
}

fn is_child_path(child: &str, parent: &str) -> bool {
    child != parent && is_same_or_child_path(child, parent)
}

/// 未纳入版本控制的目录：`svn status` 通常只返回目录本身。
/// 为了提交勾选列表，递归展开其内部文件/子目录。
fn expand_unversioned_tree(dir: &Path) -> Result<Vec<SvnStatusItem>, String> {
    let mut out = Vec::new();
    let root_name = path_file_name(dir);
    out.push(SvnStatusItem {
        path: dir.to_string_lossy().to_string(),
        name: root_name.clone(),
        status: "?".into(),
        is_dir: true,
        relative_path: root_name,
    });

    fn walk(base: &Path, current: &Path, out: &mut Vec<SvnStatusItem>) -> Result<(), String> {
        let read = fs::read_dir(current).map_err(|e| format!("读取目录失败: {e}"))?;
        for item in read {
            let item = item.map_err(|e| format!("读取目录项失败: {e}"))?;
            let name = item.file_name().to_string_lossy().to_string();
            if name == ".svn" || name == ".DS_Store" {
                continue;
            }
            let full = item.path();
            let meta = item
                .metadata()
                .map_err(|e| format!("读取元数据失败: {e}"))?;
            let relative = full
                .strip_prefix(base)
                .map(|r| {
                    let inner = r.to_string_lossy().replace('\\', "/");
                    let base_name = path_file_name(base);
                    if inner.is_empty() {
                        base_name
                    } else {
                        format!("{base_name}/{inner}")
                    }
                })
                .unwrap_or_else(|_| name.clone());
            let is_dir = meta.is_dir();
            out.push(SvnStatusItem {
                path: full.to_string_lossy().to_string(),
                name: name.clone(),
                status: "?".into(),
                is_dir,
                relative_path: relative,
            });
            if is_dir {
                walk(base, &full, out)?;
            }
        }
        Ok(())
    }

    walk(dir, dir, &mut out)?;
    Ok(out)
}

fn status_missing_path(target: &Path) -> Result<Vec<SvnStatusItem>, String> {
    let parent = target
        .parent()
        .ok_or_else(|| format!("路径不存在: {}", target.display()))?;
    if !parent.exists() {
        return Err(format!("路径不存在: {}", target.display()));
    }
    let name = path_file_name(target);
    let res = run_svn(&["status", "--depth=immediates", &name], Some(parent))?;
    let mut items = parse_status_items(&res.stdout, parent);
    let target_str = target.to_string_lossy().to_string();
    items.retain(|item| is_same_or_child_path(&item.path, &target_str));
    Ok(items)
}

/// 对单个目标（文件或文件夹）取 status。
/// - 文件：查询自身状态
/// - 文件夹：递归查询内部所有变更
/// - 未版本目录：展开内部文件，便于勾选提交
/// - 已删除/缺失路径：仍尝试从父目录读取 status
pub fn status_list(path: String, recursive: Option<bool>) -> Result<Vec<SvnStatusItem>, String> {
    let target = PathBuf::from(&path);
    let recursive = recursive.unwrap_or(true);
    let depth = if recursive { "infinity" } else { "immediates" };

    if !target.exists() {
        let mut items = status_missing_path(&target)?;
        sort_status_items(&mut items);
        return Ok(items);
    }

    if target.is_file() {
        let parent = target
            .parent()
            .ok_or_else(|| "无法解析文件父目录".to_string())?;
        let name = path_file_name(&target);
        let res = run_svn(&["status", "--depth=empty", &name], Some(parent))?;
        let mut items = parse_status_items(&res.stdout, parent);
        for item in &mut items {
            if item.path == target.to_string_lossy() {
                item.relative_path = name.clone();
            }
        }
        sort_status_items(&mut items);
        return Ok(items);
    }

    // 目录：优先在父目录对子路径执行 status（兼容 SVN 1.7+ 仅根目录有 .svn）
    // 若目标自身就是 WC 根，则在目录内执行。
    let is_wc_root = target.join(".svn").exists();
    let (res, parse_cwd) = if is_wc_root {
        (
            run_svn(&["status", &format!("--depth={depth}"), "."], Some(&target))?,
            target.clone(),
        )
    } else {
        let parent = target
            .parent()
            .ok_or_else(|| "无法解析父目录".to_string())?;
        let name = path_file_name(&target);
        (
            run_svn(
                &["status", &format!("--depth={depth}"), &name],
                Some(parent),
            )?,
            parent.to_path_buf(),
        )
    };

    // 父目录不在工作副本时，svn 可能失败；此时若本地目录存在，按未版本目录展开
    if !res.success && res.stdout.trim().is_empty() {
        if let Ok(expanded) = expand_unversioned_tree(&target) {
            let mut items = expanded;
            sort_status_items(&mut items);
            return Ok(items);
        }
        return Err(if res.stderr.trim().is_empty() {
            "获取 SVN 状态失败".into()
        } else {
            res.stderr
        });
    }

    let mut items = parse_status_items(&res.stdout, &parse_cwd);

    // 仅当目录本身是未版本控制（?）且 svn 未列出其子项时，才递归展开内部文件。
    // 注意：干净的已版本目录 status 为空，绝不能误展开成全部 ?。
    let target_str = target.to_string_lossy().to_string();
    let has_children = items
        .iter()
        .any(|item| is_child_path(&item.path, &target_str));
    let self_unversioned = items
        .iter()
        .any(|item| item.path == target_str && item.status == "?");
    if self_unversioned && !has_children {
        if let Ok(expanded) = expand_unversioned_tree(&target) {
            items = expanded;
        }
    }

    sort_status_items(&mut items);
    Ok(items)
}

/// 合并多个目标（多选文件/文件夹）的变更列表。
/// 会分别遍历每个选中文件夹内部变更，并并入选中的文件变更。
pub fn status_list_many(
    paths: Vec<String>,
    recursive: Option<bool>,
) -> Result<Vec<SvnStatusItem>, String> {
    if paths.is_empty() {
        return Err("没有可查询的路径".into());
    }
    let mut map: std::collections::BTreeMap<String, SvnStatusItem> =
        std::collections::BTreeMap::new();
    let mut errors: Vec<String> = Vec::new();
    for path in paths {
        match status_list(path.clone(), recursive) {
            Ok(items) => {
                for item in items {
                    map.entry(item.path.clone()).or_insert(item);
                }
            }
            Err(e) => errors.push(format!("{path}: {e}")),
        }
    }
    if map.is_empty() {
        if errors.is_empty() {
            return Ok(vec![]);
        }
        return Err(errors.join("\n"));
    }
    let mut items: Vec<SvnStatusItem> = map.into_values().collect();
    sort_status_items(&mut items);
    Ok(items)
}

pub fn add_paths(paths: Vec<String>) -> Result<CommandResult, String> {
    if paths.is_empty() {
        return Err("没有可添加的路径".into());
    }
    let mut args: Vec<String> = vec!["add".into(), "--force".into()];
    for p in &paths {
        let _ = ensure_path_exists(p)?;
        args.push(p.clone());
    }
    let arg_refs: Vec<&str> = args.iter().map(|s| s.as_str()).collect();
    run_svn(&arg_refs, None)
}

pub fn ignore_path(path: String) -> Result<CommandResult, String> {
    let p = ensure_path_exists(&path)?;
    let name = p
        .file_name()
        .and_then(|s| s.to_str())
        .ok_or_else(|| "无法解析文件名".to_string())?
        .to_string();
    let parent = p.parent().ok_or_else(|| "无法解析父目录".to_string())?;
    let parent_str = parent.to_string_lossy().to_string();

    // 读取现有 svn:ignore
    let existing = run_svn(&["propget", "svn:ignore", &parent_str], None);
    let mut lines: Vec<String> = Vec::new();
    if let Ok(res) = existing {
        if res.success {
            for line in res.stdout.lines() {
                let t = line.trim().to_string();
                if !t.is_empty() {
                    lines.push(t);
                }
            }
        }
    }
    if lines.iter().any(|l| l == &name) {
        return Ok(CommandResult {
            success: true,
            stdout: format!("已在忽略列表中: {name}"),
            stderr: String::new(),
            code: Some(0),
        });
    }
    lines.push(name.clone());
    lines.sort();
    lines.dedup();
    let value = format!("{}\n", lines.join("\n"));

    // 用临时方式 propset
    let args = vec![
        "propset".to_string(),
        "svn:ignore".to_string(),
        value,
        parent_str,
    ];
    let arg_refs: Vec<&str> = args.iter().map(|s| s.as_str()).collect();
    let res = run_svn(&arg_refs, None)?;
    if res.success {
        Ok(CommandResult {
            success: true,
            stdout: format!("已忽略: {name}\n{}", res.stdout),
            stderr: res.stderr,
            code: res.code,
        })
    } else {
        Ok(res)
    }
}

pub fn resolved_path(path: String) -> Result<CommandResult, String> {
    let p = ensure_path_exists(&path)?;
    run_svn(&["resolved", p.to_str().unwrap_or(&path)], None)
}

pub fn lock_paths(paths: Vec<String>, message: Option<String>) -> Result<CommandResult, String> {
    if paths.is_empty() {
        return Err("没有可锁定的路径".into());
    }
    let mut args: Vec<String> = vec!["lock".into()];
    if let Some(m) = message {
        let m = m.trim().to_string();
        if !m.is_empty() {
            args.push("-m".into());
            args.push(m);
        }
    }
    for p in &paths {
        let _ = ensure_path_exists(p)?;
        args.push(p.clone());
    }
    let arg_refs: Vec<&str> = args.iter().map(|s| s.as_str()).collect();
    run_svn(&arg_refs, None)
}

pub fn unlock_paths(paths: Vec<String>) -> Result<CommandResult, String> {
    if paths.is_empty() {
        return Err("没有可解锁的路径".into());
    }
    let mut args: Vec<String> = vec!["unlock".into()];
    for p in &paths {
        let _ = ensure_path_exists(p)?;
        args.push(p.clone());
    }
    let arg_refs: Vec<&str> = args.iter().map(|s| s.as_str()).collect();
    run_svn(&arg_refs, None)
}

pub fn switch_to(path: String, url: String) -> Result<CommandResult, String> {
    let p = ensure_path_exists(&path)?;
    let url = url.trim();
    if url.is_empty() {
        return Err("目标地址不能为空".into());
    }
    run_svn(&["switch", url, p.to_str().unwrap_or(&path)], None)
}

pub fn blame(path: String) -> Result<CommandResult, String> {
    let p = ensure_path_exists(&path)?;
    if p.is_dir() {
        return Err("注解(blame)仅支持文件".into());
    }
    run_svn(&["blame", "-x", "-w", p.to_str().unwrap_or(&path)], None)
}

pub fn create_patch(path: String) -> Result<CommandResult, String> {
    // 对工作副本/路径生成 diff patch 文本
    let p = ensure_path_exists(&path)?;
    run_svn(&["diff", p.to_str().unwrap_or(&path)], None)
}

pub fn revert(path: String) -> Result<CommandResult, String> {
    let p = ensure_path_exists(&path)?;
    run_svn(&["revert", "-R", p.to_str().unwrap_or(&path)], None)
}

pub fn clean(path: String) -> Result<CommandResult, String> {
    let p = ensure_path_exists(&path)?;
    // cleanup 目标工作副本/路径，清理锁与临时数据
    run_svn(&["cleanup", p.to_str().unwrap_or(&path)], None)
}

pub fn rename_path(path: String, new_name: String) -> Result<CommandResult, String> {
    let src = ensure_path_exists(&path)?;
    let new_name = new_name.trim();
    if new_name.is_empty() {
        return Err("新名称不能为空".into());
    }
    if new_name.contains('/') || new_name.contains('\\') {
        return Err("新名称不能包含路径分隔符".into());
    }

    let parent = src.parent().ok_or_else(|| "无法解析父目录".to_string())?;
    let dest = parent.join(new_name);
    if dest.exists() {
        return Err(format!("目标已存在: {}", dest.to_string_lossy()));
    }

    let src_str = src.to_string_lossy().to_string();
    let dest_str = dest.to_string_lossy().to_string();

    // 优先 svn move；未纳入版本控制时退回本地 rename
    match run_svn(&["move", &src_str, &dest_str], None) {
        Ok(r) if r.success => Ok(r),
        Ok(r) => {
            fs::rename(&src, &dest).map_err(|e| format!("重命名失败: {e}"))?;
            Ok(CommandResult {
                success: true,
                stdout: format!("已本地重命名: {src_str} -> {dest_str}\n{}", r.stdout),
                stderr: r.stderr,
                code: Some(0),
            })
        }
        Err(_) => {
            fs::rename(&src, &dest).map_err(|e| format!("重命名失败: {e}"))?;
            Ok(CommandResult {
                success: true,
                stdout: format!("已本地重命名: {src_str} -> {dest_str}"),
                stderr: String::new(),
                code: Some(0),
            })
        }
    }
}

/// 仅本地文件系统删除（不经过 svn）
pub fn delete_local_path(path: String) -> Result<CommandResult, String> {
    let p = ensure_path_exists(&path)?;
    let path_str = p.to_str().unwrap_or(&path).to_string();
    if p.is_dir() {
        fs::remove_dir_all(&p).map_err(|e| format!("删除文件夹失败: {e}"))?;
    } else {
        fs::remove_file(&p).map_err(|e| format!("删除文件失败: {e}"))?;
    }
    Ok(CommandResult {
        success: true,
        stdout: format!("已本地删除: {path_str}"),
        stderr: String::new(),
        code: Some(0),
    })
}

/// 仅执行 svn delete（不做本地删除回退）
pub fn delete_path(path: String, force: bool) -> Result<CommandResult, String> {
    let p = PathBuf::from(&path);
    let path_str = p.to_str().unwrap_or(&path).to_string();
    // 已版本控制但磁盘缺失（status !）时仍允许 svn delete
    if !p.exists() {
        // 若父目录也不存在则直接报错
        if let Some(parent) = p.parent() {
            if !parent.as_os_str().is_empty() && !parent.exists() {
                return Err(format!("路径不存在: {path}"));
            }
        }
    }
    if force {
        run_svn(&["delete", "--force", &path_str], None)
    } else {
        run_svn(&["delete", &path_str], None)
    }
}

pub fn diff(path: String) -> Result<CommandResult, String> {
    let p = ensure_path_exists(&path)?;
    run_svn(&["diff", p.to_str().unwrap_or(&path)], None)
}

pub fn log(path: String, limit: Option<u32>) -> Result<CommandResult, String> {
    let p = ensure_path_exists(&path)?;
    let limit_str = limit.unwrap_or(30).to_string();
    run_svn(
        &["log", "-l", &limit_str, "-v", p.to_str().unwrap_or(&path)],
        None,
    )
}

fn xml_unescape_text(raw: &[u8]) -> String {
    let text = String::from_utf8_lossy(raw);
    quick_xml::escape::unescape(&text)
        .map(|cow| cow.into_owned())
        .unwrap_or_else(|_| text.into_owned())
}

fn parse_svn_log_xml(xml: &str) -> Result<Vec<SvnLogEntry>, String> {
    let mut reader = Reader::from_str(xml);
    reader.config_mut().trim_text(false);
    let mut buf = Vec::new();
    let mut entries = Vec::new();

    let mut current_revision = String::new();
    let mut current_author: Option<String> = None;
    let mut current_date: Option<String> = None;
    let mut current_message = String::new();
    let mut current_paths: Vec<SvnLogPath> = Vec::new();
    let mut current_field: Option<&'static str> = None;
    let mut current_path: Option<SvnLogPath> = None;

    loop {
        match reader.read_event_into(&mut buf) {
            Ok(Event::Start(e)) => match e.name().as_ref() {
                b"logentry" => {
                    current_revision.clear();
                    current_author = None;
                    current_date = None;
                    current_message.clear();
                    current_paths.clear();
                    current_field = None;
                    current_path = None;
                    for attr in e.attributes().flatten() {
                        if attr.key.as_ref() == b"revision" {
                            if let Ok(value) = attr.decode_and_unescape_value(reader.decoder()) {
                                current_revision = value.into_owned();
                            }
                        }
                    }
                }
                b"author" => current_field = Some("author"),
                b"date" => current_field = Some("date"),
                b"msg" => current_field = Some("msg"),
                b"path" => {
                    let mut path = SvnLogPath {
                        path: String::new(),
                        action: String::new(),
                        kind: None,
                        copy_from_path: None,
                        copy_from_revision: None,
                    };
                    for attr in e.attributes().flatten() {
                        let key = attr.key.as_ref();
                        let value = attr
                            .decode_and_unescape_value(reader.decoder())
                            .map(|v| v.into_owned())
                            .unwrap_or_default();
                        match key {
                            b"action" => path.action = value,
                            b"kind" => path.kind = Some(value),
                            b"copyfrom-path" | b"copy-from-path" => {
                                path.copy_from_path = Some(value)
                            }
                            b"copyfrom-rev" | b"copy-from-rev" => {
                                path.copy_from_revision = Some(value)
                            }
                            _ => {}
                        }
                    }
                    current_path = Some(path);
                    current_field = Some("path");
                }
                _ => {}
            },
            Ok(Event::Text(e)) => {
                let text = normalize_svn_text(&xml_unescape_text(e.as_ref()));
                match current_field {
                    Some("author") => current_author = Some(text),
                    Some("date") => current_date = Some(text),
                    Some("msg") => {
                        if !current_message.is_empty() {
                            current_message.push('\n');
                        }
                        current_message.push_str(&text);
                    }
                    Some("path") => {
                        if let Some(path) = current_path.as_mut() {
                            path.path.push_str(&text);
                        }
                    }
                    _ => {}
                }
            }
            Ok(Event::CData(e)) => {
                let text = normalize_svn_text(&String::from_utf8_lossy(e.as_ref()));
                match current_field {
                    Some("author") => current_author = Some(text),
                    Some("date") => current_date = Some(text),
                    Some("msg") => {
                        if !current_message.is_empty() {
                            current_message.push('\n');
                        }
                        current_message.push_str(&text);
                    }
                    Some("path") => {
                        if let Some(path) = current_path.as_mut() {
                            path.path.push_str(&text);
                        }
                    }
                    _ => {}
                }
            }
            Ok(Event::End(e)) => match e.name().as_ref() {
                b"path" => {
                    if let Some(path) = current_path.take() {
                        current_paths.push(path);
                    }
                    current_field = None;
                }
                b"author" | b"date" | b"msg" => current_field = None,
                b"logentry" => {
                    if !current_revision.is_empty() {
                        entries.push(SvnLogEntry {
                            revision: current_revision.clone(),
                            author: current_author.clone(),
                            date: current_date.clone(),
                            message: current_message.trim().to_string(),
                            paths: current_paths.clone(),
                        });
                    }
                    current_field = None;
                    current_path = None;
                }
                _ => {}
            },
            Ok(Event::Eof) => break,
            Err(e) => return Err(format!("解析 svn log XML 失败: {e}")),
            _ => {}
        }
        buf.clear();
    }

    Ok(entries)
}

pub fn log_entries(path: String, limit: Option<u32>) -> Result<Vec<SvnLogEntry>, String> {
    let p = ensure_path_exists(&path)?;
    let limit_str = limit.unwrap_or(30).to_string();
    let res = run_svn(
        &[
            "log",
            "--xml",
            "-v",
            "-l",
            &limit_str,
            p.to_str().unwrap_or(&path),
        ],
        None,
    )?;
    if !res.success && res.stdout.trim().is_empty() {
        return Err(if res.stderr.trim().is_empty() {
            "读取日志失败".into()
        } else {
            res.stderr
        });
    }
    parse_svn_log_xml(&res.stdout)
}

fn svn_show_item(path: &Path, item: &str) -> Result<String, String> {
    let svn = svn_binary();
    let mut cmd = Command::new(svn);
    cmd.args([
        "info",
        "--show-item",
        item,
        path.to_str().unwrap_or_default(),
    ]);
    apply_svn_locale(&mut cmd);
    let output = cmd
        .output()
        .map_err(|e| format!("执行 svn info 失败: {e}"))?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).trim().to_string());
    }
    Ok(normalize_svn_text(
        &String::from_utf8_lossy(&output.stdout).trim().to_string(),
    ))
}

fn svn_cat_revision_text(path: &Path, rev: &str) -> Result<(bool, Vec<u8>, bool), String> {
    svn_cat_revision(path, rev)
}

pub fn revision_diff_file_content(
    path: String,
    revision: String,
    action: Option<String>,
) -> Result<DiffFileContent, String> {
    let target = ensure_path_exists(&path)?;
    if target.is_dir() {
        return Err("目录无法展示历史 Diff".into());
    }

    let root = find_wc_root(&target).unwrap_or_else(|| {
        target
            .parent()
            .map(|p| p.to_path_buf())
            .unwrap_or_else(|| target.clone())
    });
    let relative = relative_to_root(&root, &target);
    let name = target
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or(&path)
        .to_string();
    let language = guess_language(&target);
    let status = action.clone().unwrap_or_else(|| "M".into());
    let status_label = map_status_label(&status);

    let url = svn_show_item(&target, "url")?;
    let rev_num = revision.trim();
    if rev_num.is_empty() {
        return Err("修订号不能为空".into());
    }
    let prev_rev = rev_num.parse::<i64>().ok().and_then(|n| {
        if n > 1 {
            Some((n - 1).to_string())
        } else {
            None
        }
    });

    let (old_exists, old_bytes, old_over, new_exists, new_bytes, new_over) = match status.as_str() {
        "A" => {
            let new = svn_cat_revision_text(Path::new(&url), rev_num)?;
            (false, Vec::new(), false, new.0, new.1, new.2)
        }
        "D" | "!" => {
            let old = if let Some(prev) = prev_rev.as_deref() {
                svn_cat_revision_text(Path::new(&url), prev)?
            } else {
                (false, Vec::new(), false)
            };
            (old.0, old.1, old.2, false, Vec::new(), false)
        }
        _ => {
            let old = if let Some(prev) = prev_rev.as_deref() {
                svn_cat_revision_text(Path::new(&url), prev)?
            } else {
                (false, Vec::new(), false)
            };
            let new = svn_cat_revision_text(Path::new(&url), rev_num)?;
            (old.0, old.1, old.2, new.0, new.1, new.2)
        }
    };

    let oversized = old_over || new_over;
    let binary = oversized
        || (old_exists && bytes_look_binary(&old_bytes))
        || (new_exists && bytes_look_binary(&new_bytes));

    if binary {
        return Ok(DiffFileContent {
            path,
            relative_path: relative,
            name,
            status,
            status_label,
            binary: true,
            old_text: String::new(),
            new_text: String::new(),
            old_exists,
            new_exists,
            language,
            message: Some(if oversized {
                format!("修订 {revision} 的文件过大（> 2MB），不展示文本 Diff")
            } else {
                format!("修订 {revision} 的二进制文件，无法展示文本 Diff")
            }),
        });
    }

    Ok(DiffFileContent {
        path,
        relative_path: relative,
        name,
        status,
        status_label,
        binary: false,
        old_text: if old_exists {
            String::from_utf8_lossy(&old_bytes).to_string()
        } else {
            String::new()
        },
        new_text: if new_exists {
            String::from_utf8_lossy(&new_bytes).to_string()
        } else {
            String::new()
        },
        old_exists,
        new_exists,
        language,
        message: None,
    })
}

pub fn proplist(path: String) -> Result<CommandResult, String> {
    let p = ensure_path_exists(&path)?;
    run_svn(&["proplist", "-v", p.to_str().unwrap_or(&path)], None)
}

pub fn info(path: String) -> Result<CommandResult, String> {
    let p = ensure_path_exists(&path)?;
    run_svn(&["info", p.to_str().unwrap_or(&path)], None)
}

pub fn reveal_in_finder(path: String) -> Result<(), String> {
    let p = ensure_path_exists(&path)?;
    let status = Command::new("open")
        .args(["-R", p.to_str().unwrap_or(&path)])
        .status()
        .map_err(|e| format!("无法在 Finder 中显示: {e}"))?;
    if !status.success() {
        return Err("在 Finder 中显示失败".into());
    }
    Ok(())
}

pub fn preview_file(path: String) -> Result<PreviewPayload, String> {
    let p = ensure_path_exists(&path)?;
    if p.is_dir() {
        let count = fs::read_dir(&p)
            .map(|rd| {
                rd.filter_map(|e| e.ok())
                    .filter(|e| e.file_name() != ".svn")
                    .count()
            })
            .unwrap_or(0);
        return Ok(PreviewPayload {
            kind: "directory".into(),
            path: path.clone(),
            name: p
                .file_name()
                .and_then(|s| s.to_str())
                .unwrap_or(&path)
                .to_string(),
            size: 0,
            mime: None,
            content: None,
            data_url: None,
            message: Some(format!("文件夹 · {count} 项")),
        });
    }

    let meta = fs::metadata(&p).map_err(|e| format!("读取文件失败: {e}"))?;
    let size = meta.len();
    let name = p
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or(&path)
        .to_string();
    let ext = extension_of(&p).unwrap_or_default();
    let mime = guess_mime(&ext).to_string();

    if size > 5 * 1024 * 1024 {
        return Ok(PreviewPayload {
            kind: "large".into(),
            path,
            name,
            size,
            mime: Some(mime),
            content: None,
            data_url: None,
            message: Some("文件过大，暂不预览（> 5MB）".into()),
        });
    }

    let bytes = fs::read(&p).map_err(|e| format!("读取文件内容失败: {e}"))?;

    if is_image_ext(&ext) {
        let data_url = format!("data:{};base64,{}", mime, BASE64.encode(&bytes));
        return Ok(PreviewPayload {
            kind: "image".into(),
            path,
            name,
            size,
            mime: Some(mime),
            content: None,
            data_url: Some(data_url),
            message: None,
        });
    }

    if is_text_ext(&ext) || looks_like_text(&bytes) {
        let content = String::from_utf8_lossy(&bytes).to_string();
        return Ok(PreviewPayload {
            kind: "text".into(),
            path,
            name,
            size,
            mime: Some(mime),
            content: Some(content),
            data_url: None,
            message: None,
        });
    }

    Ok(PreviewPayload {
        kind: "binary".into(),
        path,
        name,
        size,
        mime: Some(mime),
        content: None,
        data_url: None,
        message: Some("二进制文件，无法预览".into()),
    })
}

fn map_status_label(code: &str) -> String {
    match code {
        "A" => "added".into(),
        "D" | "!" => "deleted".into(),
        "?" => "unversioned".into(),
        "R" => "replaced".into(),
        "C" => "conflicted".into(),
        "M" | "~" => "modified".into(),
        _ => "modified".into(),
    }
}

fn guess_language(path: &Path) -> String {
    let ext = extension_of(path).unwrap_or_default();
    match ext.as_str() {
        "js" | "mjs" | "cjs" | "jsx" => "javascript".into(),
        "ts" | "tsx" | "mts" | "cts" => "typescript".into(),
        "vue" => "vue".into(),
        "json" | "jsonc" | "json5" => "json".into(),
        "md" | "markdown" | "mdx" => "markdown".into(),
        "py" | "pyw" => "python".into(),
        "rs" => "rust".into(),
        "java" => "java".into(),
        "kt" | "kts" => "kotlin".into(),
        "groovy" | "gvy" | "gy" | "gsh" => "groovy".into(),
        "gradle" => "gradle".into(),
        "go" => "go".into(),
        "rb" | "erb" => "ruby".into(),
        "php" | "phtml" => "php".into(),
        "c" | "h" => "c".into(),
        "cpp" | "cc" | "cxx" | "hpp" | "hh" | "hxx" => "cpp".into(),
        "cs" => "csharp".into(),
        "swift" => "swift".into(),
        "m" | "mm" => "objectivec".into(),
        "scala" | "sc" => "scala".into(),
        "lua" => "lua".into(),
        "pl" | "pm" => "perl".into(),
        "r" => "r".into(),
        "dart" => "dart".into(),
        "vb" | "vbs" => "vbnet".into(),
        "sh" | "bash" | "zsh" | "ksh" => "bash".into(),
        "shell" => "shell".into(),
        "bat" | "cmd" => "dos".into(),
        "ps1" | "psm1" | "psd1" => "powershell".into(),
        "sql" | "ddl" | "dml" => "sql".into(),
        "yml" | "yaml" => "yaml".into(),
        "toml" => "toml".into(),
        "ini" | "cfg" | "conf" => "ini".into(),
        "properties" | "prop" | "mf" => "properties".into(),
        // FreeMarker / JSP stack commonly used by CCF member project
        "ftl" | "ftlh" | "ftlx" => "ftl".into(),
        "jsp" | "jspf" | "jspx" | "tag" | "tagx" => "jsp".into(),
        "tld" => "tld".into(),
        "xml" | "xsl" | "xslt" | "xsd" | "wsdl" | "plist" | "iml" => "xml".into(),
        "html" | "htm" | "xhtml" => "html".into(),
        "svg" => "svg".into(),
        "css" => "css".into(),
        "scss" | "sass" => "scss".into(),
        "less" => "less".into(),
        "diff" | "patch" => "diff".into(),
        "http" => "http".into(),
        "nginx" => "nginx".into(),
        "dockerfile" => "dockerfile".into(),
        "makefile" | "mk" => "makefile".into(),
        "env" => "env".into(),
        "txt" | "log" | "gitignore" | "gitattributes" | "editorconfig" | "npmrc" | "nvmrc"
        | "classpath" | "project" | "prefs" | "bak" => "plaintext".into(),
        _ => {
            let name = path
                .file_name()
                .and_then(|s| s.to_str())
                .unwrap_or("")
                .to_lowercase();
            if name == "dockerfile" || name.starts_with("dockerfile.") {
                "dockerfile".into()
            } else if name == "makefile" || name == "gnumakefile" || name == "cmakelists.txt" {
                "makefile".into()
            } else if name == "pom.xml" {
                "xml".into()
            } else if name == "build.gradle" || name == "settings.gradle" {
                "gradle".into()
            } else if name == "build.gradle.kts" || name == "settings.gradle.kts" {
                "kotlin".into()
            } else if name == "nginx.conf" || name.ends_with(".nginx") {
                "nginx".into()
            } else if name == ".env" || name.starts_with(".env.") {
                "properties".into()
            } else if name == "manifest.mf" {
                "properties".into()
            } else {
                "plaintext".into()
            }
        }
    }
}

fn bytes_look_binary(bytes: &[u8]) -> bool {
    if bytes.is_empty() {
        return false;
    }
    if bytes.contains(&0) {
        return true;
    }
    !looks_like_text(bytes)
}

fn read_working_bytes(path: &Path) -> Result<(bool, Vec<u8>, bool), String> {
    // returns (exists, bytes, oversized)
    if !path.exists() {
        return Ok((false, Vec::new(), false));
    }
    if path.is_dir() {
        return Ok((true, Vec::new(), false));
    }
    let meta = fs::metadata(path).map_err(|e| format!("读取文件失败: {e}"))?;
    if meta.len() > 2 * 1024 * 1024 {
        return Ok((true, Vec::new(), true));
    }
    let bytes = fs::read(path).map_err(|e| format!("读取文件内容失败: {e}"))?;
    Ok((true, bytes, false))
}

fn svn_cat_revision(path: &Path, rev: &str) -> Result<(bool, Vec<u8>, bool), String> {
    // returns (exists, bytes, oversized)
    let svn = svn_binary();
    let path_str = path.to_string_lossy().to_string();
    let mut cmd = Command::new(svn);
    cmd.args(["cat", "-r", rev, &path_str]);
    apply_svn_locale(&mut cmd);
    cmd.stdout(Stdio::piped()).stderr(Stdio::piped());
    let output = cmd
        .output()
        .map_err(|e| format!("执行 svn cat 失败: {e}"))?;
    if !output.status.success() {
        return Ok((false, Vec::new(), false));
    }
    if output.stdout.len() > 2 * 1024 * 1024 {
        return Ok((true, Vec::new(), true));
    }
    Ok((true, output.stdout, false))
}

fn relative_to_root(root: &Path, full: &Path) -> String {
    full.strip_prefix(root)
        .map(|r| r.to_string_lossy().to_string())
        .unwrap_or_else(|_| {
            full.file_name()
                .and_then(|s| s.to_str())
                .unwrap_or_default()
                .to_string()
        })
}

fn find_wc_root(start: &Path) -> Option<PathBuf> {
    let mut cur = if start.is_file() {
        start.parent().map(|p| p.to_path_buf())?
    } else {
        start.to_path_buf()
    };
    loop {
        if cur.join(".svn").exists() {
            return Some(cur);
        }
        if !cur.pop() {
            break;
        }
    }
    None
}

fn detect_binary(path: &Path, status_code: &str) -> Result<bool, String> {
    if path.is_dir() {
        return Ok(false);
    }
    let (new_exists, new_bytes, new_over) = read_working_bytes(path)?;
    let need_base = !(status_code == "?" || status_code == "A");
    let (old_exists, old_bytes, old_over) = if need_base {
        svn_cat_revision(path, "BASE")?
    } else {
        (false, Vec::new(), false)
    };
    if new_over || old_over {
        return Ok(true);
    }
    if (new_exists && bytes_look_binary(&new_bytes))
        || (old_exists && bytes_look_binary(&old_bytes))
    {
        return Ok(true);
    }
    Ok(false)
}

fn build_file_info_from_path(
    root: &Path,
    full: &Path,
    status_code: &str,
) -> Result<DiffFileInfo, String> {
    let is_dir = full.is_dir();
    let name = full
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or_default()
        .to_string();
    let relative = relative_to_root(root, full);
    let status_label = map_status_label(status_code);
    let binary = if is_dir {
        false
    } else {
        detect_binary(full, status_code).unwrap_or(false)
    };
    Ok(DiffFileInfo {
        path: full.to_string_lossy().to_string(),
        relative_path: relative,
        name,
        status: status_code.to_string(),
        status_label,
        binary,
        is_dir,
    })
}

/// 列出路径下可展示 DIFF 的文件（目录则展开状态变更）
pub fn diff_files(path: String) -> Result<Vec<DiffFileInfo>, String> {
    let target = PathBuf::from(&path);

    if target.exists() && target.is_file() {
        let root = find_wc_root(&target).unwrap_or_else(|| {
            target
                .parent()
                .map(|p| p.to_path_buf())
                .unwrap_or_else(|| target.clone())
        });
        let code = status_of(&path)?.unwrap_or_else(|| "M".into());
        return Ok(vec![build_file_info_from_path(&root, &target, &code)?]);
    }

    if !target.exists() {
        // 可能是已删除文件
        let parent = target
            .parent()
            .map(|p| p.to_path_buf())
            .unwrap_or_else(|| PathBuf::from("."));
        let root = find_wc_root(&parent).unwrap_or(parent);
        let code = status_of(&path)?.unwrap_or_else(|| "D".into());
        return Ok(vec![build_file_info_from_path(&root, &target, &code)?]);
    }

    // 目录：基于 status 列表展开变更文件
    let root = find_wc_root(&target).unwrap_or_else(|| target.clone());
    let items = status_list(path, Some(true))?;
    let mut files = Vec::new();
    for item in items {
        if item.is_dir || item.status == "X" || item.status == "I" {
            continue;
        }
        let full = PathBuf::from(&item.path);
        if let Ok(info) = build_file_info_from_path(&root, &full, &item.status) {
            files.push(info);
        }
    }
    files.sort_by(|a, b| {
        a.relative_path
            .to_lowercase()
            .cmp(&b.relative_path.to_lowercase())
    });
    Ok(files)
}

/// 读取单个文件 BASE vs 工作副本内容
pub fn diff_file_content(path: String) -> Result<DiffFileContent, String> {
    let target = PathBuf::from(&path);
    let probe = if target.exists() {
        target.clone()
    } else {
        target
            .parent()
            .map(|p| p.to_path_buf())
            .unwrap_or_else(|| PathBuf::from("."))
    };
    let root = find_wc_root(&probe).unwrap_or(probe);
    let code = status_of(&path)?.unwrap_or_else(|| {
        if target.exists() {
            "M".into()
        } else {
            "D".into()
        }
    });
    let status_label = map_status_label(&code);
    let name = target
        .file_name()
        .and_then(|s| s.to_str())
        .unwrap_or(&path)
        .to_string();
    let relative = relative_to_root(&root, &target);
    let language = guess_language(&target);

    if target.exists() && target.is_dir() {
        return Ok(DiffFileContent {
            path,
            relative_path: relative,
            name,
            status: code,
            status_label,
            binary: false,
            old_text: String::new(),
            new_text: String::new(),
            old_exists: false,
            new_exists: true,
            language,
            message: Some("目录无法展示文本 Diff".into()),
        });
    }

    let (new_exists, new_bytes, new_over) = read_working_bytes(&target)?;
    let (old_exists, old_bytes, old_over) = if code == "?" || code == "A" {
        (false, Vec::new(), false)
    } else {
        svn_cat_revision(&target, "BASE")?
    };

    let oversized = new_over || old_over;
    let binary = oversized
        || (old_exists && bytes_look_binary(&old_bytes))
        || (new_exists && bytes_look_binary(&new_bytes));

    if binary {
        return Ok(DiffFileContent {
            path,
            relative_path: relative,
            name,
            status: code,
            status_label,
            binary: true,
            old_text: String::new(),
            new_text: String::new(),
            old_exists,
            new_exists,
            language,
            message: Some(if oversized {
                "文件过大（> 2MB），不展示文本 Diff".into()
            } else {
                "二进制文件，无法展示文本 Diff".into()
            }),
        });
    }

    let old_text = if old_exists {
        String::from_utf8_lossy(&old_bytes).to_string()
    } else {
        String::new()
    };
    let new_text = if new_exists {
        String::from_utf8_lossy(&new_bytes).to_string()
    } else {
        String::new()
    };

    Ok(DiffFileContent {
        path,
        relative_path: relative,
        name,
        status: code,
        status_label,
        binary: false,
        old_text,
        new_text,
        old_exists,
        new_exists,
        language,
        message: None,
    })
}

pub fn is_svn_working_copy(path: String) -> Result<bool, String> {
    let p = PathBuf::from(path);
    Ok(p.is_dir() && p.join(".svn").exists())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn decode_svn_unicode_path_escapes() {
        let escaped =
            "java/{U+4F1A}{U+5458}{U+4FE1}{U+606F}{U+7F16}{U+8F91}{U+9875}{U+9762}{U+89D2}{U+8272}{U+5BF9}{U+7167}.md";
        assert_eq!(
            decode_svn_unicode_escapes(escaped),
            "java/会员信息编辑页面角色对照.md"
        );
    }

    #[test]
    fn decode_leaves_plain_utf8_paths() {
        let plain = "java/会员信息编辑页面角色对照.md";
        assert_eq!(decode_svn_unicode_escapes(plain), plain);
    }
}
