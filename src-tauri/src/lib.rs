mod svn;
mod workspace;

use svn::{CommandResult, FsEntry, PreviewPayload};
use tauri::AppHandle;
use workspace::Workspace;

#[tauri::command]
fn list_workspaces() -> Result<Vec<Workspace>, String> {
    workspace::list_workspaces()
}

#[tauri::command]
fn add_workspace(path: String, name: Option<String>) -> Result<Workspace, String> {
    workspace::add_existing_workspace(path, name)
}

#[tauri::command]
fn remove_workspace(id: String) -> Result<(), String> {
    workspace::remove_workspace(id)
}

#[tauri::command]
fn rename_workspace(id: String, name: String) -> Result<workspace::Workspace, String> {
    workspace::rename_workspace(id, name)
}

/// 异步检出：立刻返回，进度通过 svn-progress 事件推送，结束时 phase=done/error。
#[tauri::command]
fn checkout_workspace(
    app: AppHandle,
    job_id: String,
    url: String,
    path: String,
    name: Option<String>,
) -> Result<(), String> {
    // 启动前先做轻量校验，避免无效任务
    if url.trim().is_empty() {
        return Err("SVN 地址不能为空".into());
    }
    if path.trim().is_empty() {
        return Err("本地目录不能为空".into());
    }

    let app_bg = app.clone();
    let job = job_id.clone();
    std::thread::spawn(move || {
        match svn::checkout(&app_bg, &job, url.clone(), path.clone()) {
            Ok(result) if result.success => {
                match workspace::add_checkout_workspace(path, url, name) {
                    Ok(_) => {
                        // 工作区入库后再发 done，前端此时刷新能看到新条目
                        svn::emit_job_done(&app_bg, &job, true, "检出完成");
                    }
                    Err(e) => {
                        svn::emit_job_error(
                            &app_bg,
                            &job,
                            &format!("检出成功但添加工作区失败: {e}"),
                        );
                    }
                }
            }
            Ok(result) => {
                let msg = if !result.stderr.trim().is_empty() {
                    result.stderr
                } else if !result.stdout.trim().is_empty() {
                    result.stdout
                } else {
                    "检出失败".into()
                };
                svn::emit_job_error(&app_bg, &job, &format!("检出失败: {}", msg.trim()));
            }
            Err(e) => {
                svn::emit_job_error(&app_bg, &job, &e);
            }
        }
    });

    Ok(())
}

#[tauri::command]
fn list_directory(path: String) -> Result<Vec<FsEntry>, String> {
    svn::list_directory(path)
}

/// 异步更新：立刻返回，进度通过 svn-progress 事件推送。
#[tauri::command]
fn svn_update(app: AppHandle, job_id: String, path: String) -> Result<(), String> {
    if path.trim().is_empty() {
        return Err("路径不能为空".into());
    }
    let app_bg = app.clone();
    let job = job_id.clone();
    std::thread::spawn(move || {
        if let Err(e) = svn::update(&app_bg, &job, path) {
            svn::emit_job_error(&app_bg, &job, &e);
        }
    });
    Ok(())
}

#[tauri::command]
fn svn_commit(
    path: String,
    message: String,
    paths: Option<Vec<String>>,
) -> Result<CommandResult, String> {
    if message.trim().is_empty() {
        return Err("提交说明不能为空".into());
    }
    svn::commit(path, message, paths)
}

#[tauri::command]
fn svn_status(path: String, recursive: Option<bool>) -> Result<Vec<svn::SvnStatusItem>, String> {
    svn::status_list(path, recursive)
}

#[tauri::command]
fn svn_status_many(paths: Vec<String>, recursive: Option<bool>) -> Result<Vec<svn::SvnStatusItem>, String> {
    if paths.is_empty() {
        return Err("没有可查询的路径".into());
    }
    svn::status_list_many(paths, recursive)
}

#[tauri::command]
fn svn_add(paths: Vec<String>) -> Result<CommandResult, String> {
    if paths.is_empty() {
        return Err("没有可添加的路径".into());
    }
    svn::add_paths(paths)
}

#[tauri::command]
fn svn_ignore(path: String) -> Result<CommandResult, String> {
    svn::ignore_path(path)
}

#[tauri::command]
fn svn_resolved(path: String) -> Result<CommandResult, String> {
    svn::resolved_path(path)
}

#[tauri::command]
fn svn_lock(paths: Vec<String>, message: Option<String>) -> Result<CommandResult, String> {
    if paths.is_empty() {
        return Err("没有可锁定的路径".into());
    }
    svn::lock_paths(paths, message)
}

#[tauri::command]
fn svn_unlock(paths: Vec<String>) -> Result<CommandResult, String> {
    if paths.is_empty() {
        return Err("没有可解锁的路径".into());
    }
    svn::unlock_paths(paths)
}

#[tauri::command]
fn svn_switch(path: String, url: String) -> Result<CommandResult, String> {
    if url.trim().is_empty() {
        return Err("目标地址不能为空".into());
    }
    svn::switch_to(path, url)
}

#[tauri::command]
fn svn_blame(path: String) -> Result<CommandResult, String> {
    svn::blame(path)
}

#[tauri::command]
fn svn_patch(path: String) -> Result<CommandResult, String> {
    svn::create_patch(path)
}

#[tauri::command]
fn svn_revert(path: String) -> Result<CommandResult, String> {
    svn::revert(path)
}

#[tauri::command]
fn svn_delete(path: String, force: Option<bool>) -> Result<CommandResult, String> {
    svn::delete_path(path, force.unwrap_or(true))
}

#[tauri::command]
fn svn_clean(path: String) -> Result<CommandResult, String> {
    svn::clean(path)
}

#[tauri::command]
fn svn_rename(path: String, new_name: String) -> Result<CommandResult, String> {
    if new_name.trim().is_empty() {
        return Err("新名称不能为空".into());
    }
    svn::rename_path(path, new_name)
}

#[tauri::command]
fn svn_diff(path: String) -> Result<CommandResult, String> {
    svn::diff(path)
}

#[tauri::command]
fn svn_diff_files(path: String) -> Result<Vec<svn::DiffFileInfo>, String> {
    svn::diff_files(path)
}

#[tauri::command]
fn svn_diff_file_content(path: String) -> Result<svn::DiffFileContent, String> {
    svn::diff_file_content(path)
}

#[tauri::command]
fn svn_log(path: String, limit: Option<u32>) -> Result<CommandResult, String> {
    svn::log(path, limit)
}

#[tauri::command]
fn svn_proplist(path: String) -> Result<CommandResult, String> {
    svn::proplist(path)
}

#[tauri::command]
fn svn_info(path: String) -> Result<CommandResult, String> {
    svn::info(path)
}

#[tauri::command]
fn reveal_in_finder(path: String) -> Result<(), String> {
    svn::reveal_in_finder(path)
}

#[tauri::command]
fn preview_file(path: String) -> Result<PreviewPayload, String> {
    svn::preview_file(path)
}

#[tauri::command]
fn is_svn_working_copy(path: String) -> Result<bool, String> {
    svn::is_svn_working_copy(path)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            list_workspaces,
            add_workspace,
            remove_workspace,
            rename_workspace,
            checkout_workspace,
            list_directory,
            svn_update,
            svn_commit,
            svn_status,
            svn_status_many,
            svn_add,
            svn_ignore,
            svn_resolved,
            svn_lock,
            svn_unlock,
            svn_switch,
            svn_blame,
            svn_patch,
            svn_revert,
            svn_delete,
            svn_clean,
            svn_rename,
            svn_diff,
            svn_diff_files,
            svn_diff_file_content,
            svn_log,
            svn_proplist,
            svn_info,
            reveal_in_finder,
            preview_file,
            is_svn_working_copy
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
