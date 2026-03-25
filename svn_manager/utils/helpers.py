"""
工具函数 - 时间格式化、路径处理等
"""
from datetime import datetime, timezone
import os


def format_date(iso_str: str) -> str:
    """将 SVN ISO 日期字符串格式化为本地时间"""
    if not iso_str:
        return ""
    try:
        # SVN 输出格式: 2024-01-15T10:30:45.123456Z
        iso_str = iso_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_str)
        local_dt = dt.astimezone()
        return local_dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return iso_str[:19].replace("T", " ")


def shorten_path(path: str, max_len: int = 50) -> str:
    """缩短过长路径"""
    if len(path) <= max_len:
        return path
    parts = path.split(os.sep)
    if len(parts) > 3:
        return os.sep.join([parts[0], "...", parts[-2], parts[-1]])
    return "..." + path[-(max_len - 3):]


def file_size_str(size: int) -> str:
    """格式化文件大小"""
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def is_binary_file(path: str, sample_size: int = 8192) -> bool:
    """简单判断是否为二进制文件"""
    try:
        with open(path, "rb") as f:
            chunk = f.read(sample_size)
        return b"\x00" in chunk
    except Exception:
        return False


def get_file_icon_name(path: str) -> str:
    """根据文件扩展名返回图标名"""
    ext = os.path.splitext(path)[1].lower()
    mapping = {
        ".py": "python", ".js": "javascript", ".ts": "typescript",
        ".java": "java", ".kt": "kotlin", ".swift": "swift",
        ".c": "c", ".cpp": "cpp", ".h": "header",
        ".html": "html", ".css": "css", ".xml": "xml", ".json": "json",
        ".md": "markdown", ".txt": "text",
        ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image",
        ".svg": "image", ".ico": "image",
        ".pdf": "pdf",
        ".zip": "archive", ".tar": "archive", ".gz": "archive",
        ".mp3": "audio", ".wav": "audio",
        ".mp4": "video", ".mov": "video",
    }
    return mapping.get(ext, "file")
