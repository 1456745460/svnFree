use chrono::Utc;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct Workspace {
    pub id: String,
    pub name: String,
    pub path: String,
    pub url: Option<String>,
    pub created_at: String,
}

#[derive(Debug, Default, Serialize, Deserialize)]
struct WorkspaceStore {
    workspaces: Vec<Workspace>,
}

fn store_path() -> Result<PathBuf, String> {
    let base = dirs::data_dir()
        .or_else(dirs::home_dir)
        .ok_or_else(|| "无法定位应用数据目录".to_string())?;
    let dir = base.join("svn-free");
    fs::create_dir_all(&dir).map_err(|e| format!("创建数据目录失败: {e}"))?;
    Ok(dir.join("workspaces.json"))
}

fn load_store() -> Result<WorkspaceStore, String> {
    let path = store_path()?;
    if !path.exists() {
        return Ok(WorkspaceStore::default());
    }
    let raw = fs::read_to_string(&path).map_err(|e| format!("读取工作副本配置失败: {e}"))?;
    if raw.trim().is_empty() {
        return Ok(WorkspaceStore::default());
    }
    serde_json::from_str(&raw).map_err(|e| format!("解析工作副本配置失败: {e}"))
}

fn save_store(store: &WorkspaceStore) -> Result<(), String> {
    let path = store_path()?;
    let raw = serde_json::to_string_pretty(store).map_err(|e| format!("序列化失败: {e}"))?;
    fs::write(path, raw).map_err(|e| format!("保存工作副本配置失败: {e}"))
}

pub fn list_workspaces() -> Result<Vec<Workspace>, String> {
    Ok(load_store()?.workspaces)
}

pub fn add_existing_workspace(path: String, name: Option<String>) -> Result<Workspace, String> {
    let path_buf = PathBuf::from(&path);
    if !path_buf.is_dir() {
        return Err("所选路径不是有效文件夹".into());
    }
    if !path_buf.join(".svn").exists() {
        return Err("所选路径不是 SVN 工作副本（缺少 .svn 目录）".into());
    }

    let mut store = load_store()?;
    if store.workspaces.iter().any(|w| w.path == path) {
        return Err("该工作副本已添加".into());
    }

    let display_name = name.unwrap_or_else(|| {
        path_buf
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("工作副本")
            .to_string()
    });

    let workspace = Workspace {
        id: Uuid::new_v4().to_string(),
        name: display_name,
        path,
        url: None,
        created_at: Utc::now().to_rfc3339(),
    };
    store.workspaces.push(workspace.clone());
    save_store(&store)?;
    Ok(workspace)
}

pub fn add_checkout_workspace(
    path: String,
    url: String,
    name: Option<String>,
) -> Result<Workspace, String> {
    let path_buf = PathBuf::from(&path);
    if !path_buf.exists() {
        fs::create_dir_all(&path_buf).map_err(|e| format!("创建检出目录失败: {e}"))?;
    }

    let mut store = load_store()?;
    if store.workspaces.iter().any(|w| w.path == path) {
        return Err("该本地路径已作为工作副本存在".into());
    }

    let display_name = name.unwrap_or_else(|| {
        Path::new(&path)
            .file_name()
            .and_then(|s| s.to_str())
            .unwrap_or("工作副本")
            .to_string()
    });

    let workspace = Workspace {
        id: Uuid::new_v4().to_string(),
        name: display_name,
        path,
        url: Some(url),
        created_at: Utc::now().to_rfc3339(),
    };
    store.workspaces.push(workspace.clone());
    save_store(&store)?;
    Ok(workspace)
}

pub fn remove_workspace(id: String) -> Result<(), String> {
    let mut store = load_store()?;
    let before = store.workspaces.len();
    store.workspaces.retain(|w| w.id != id);
    if store.workspaces.len() == before {
        return Err("未找到指定工作副本".into());
    }
    save_store(&store)
}

pub fn rename_workspace(id: String, name: String) -> Result<Workspace, String> {
    let name = name.trim().to_string();
    if name.is_empty() {
        return Err("名称不能为空".into());
    }
    let mut store = load_store()?;
    let ws = store
        .workspaces
        .iter_mut()
        .find(|w| w.id == id)
        .ok_or_else(|| "未找到指定工作副本".to_string())?;
    ws.name = name;
    let cloned = ws.clone();
    save_store(&store)?;
    Ok(cloned)
}
