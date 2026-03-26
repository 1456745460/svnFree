"""
文件图标提供器 - 基于 qtawesome (FontAwesome 6 / Material Design Icons)
为不同后缀名的文件返回对应的 QIcon 和颜色，效果类似 VS Code 文件树。
"""
from __future__ import annotations

from functools import lru_cache

try:
    import qtawesome as qta
    _QTA_AVAILABLE = True
except ImportError:
    _QTA_AVAILABLE = False

from PyQt6.QtGui import QIcon, QPixmap, QColor, QPainter
from PyQt6.QtCore import Qt, QSize


# ── 后缀 → (图标名, 颜色十六进制) ────────────────────────────────────────
# 优先使用 mdi6（Material Design Icons 6），回退到 fa6s（FontAwesome 6 Solid）

_EXT_MAP: dict[str, tuple[str, str]] = {
    # ── Python ──
    ".py":    ("mdi6.language-python",    "#3572A5"),
    ".pyw":   ("mdi6.language-python",    "#3572A5"),
    ".pyc":   ("mdi6.language-python",    "#6c7086"),

    # ── JavaScript / TypeScript ──
    ".js":    ("mdi6.language-javascript","#F7DF1E"),
    ".mjs":   ("mdi6.language-javascript","#F7DF1E"),
    ".cjs":   ("mdi6.language-javascript","#F7DF1E"),
    ".ts":    ("mdi6.language-typescript","#3178C6"),
    ".tsx":   ("mdi6.react",              "#61DAFB"),
    ".jsx":   ("mdi6.react",              "#61DAFB"),
    ".vue":   ("mdi6.vuejs",              "#41B883"),

    # ── Web ──
    ".html":  ("mdi6.language-html5",     "#E34F26"),
    ".htm":   ("mdi6.language-html5",     "#E34F26"),
    ".css":   ("mdi6.language-css3",      "#1572B6"),
    ".scss":  ("mdi6.sass",               "#CF649A"),
    ".sass":  ("mdi6.sass",               "#CF649A"),
    ".less":  ("mdi6.less",               "#1D365D"),
    ".svg":   ("mdi6.svg",                "#FFB13B"),

    # ── Java ──
    ".java":  ("mdi6.language-java",      "#B07219"),
    ".class": ("mdi6.language-java",      "#6c7086"),
    ".jar":   ("mdi6.package-variant",    "#B07219"),
    ".war":   ("mdi6.package-variant",    "#B07219"),
    ".gradle":("mdi6.elephant",           "#02303A"),
    ".kt":    ("mdi6.language-kotlin",    "#7F52FF"),
    ".kts":   ("mdi6.language-kotlin",    "#7F52FF"),

    # ── C / C++ / C# / Rust / Go ──
    ".c":     ("mdi6.language-c",         "#555555"),
    ".h":     ("mdi6.language-c",         "#555555"),
    ".cpp":   ("mdi6.language-cpp",       "#f34b7d"),
    ".cc":    ("mdi6.language-cpp",       "#f34b7d"),
    ".hpp":   ("mdi6.language-cpp",       "#f34b7d"),
    ".cs":    ("mdi6.language-csharp",    "#178600"),
    ".rs":    ("mdi6.language-rust",      "#DEA584"),
    ".go":    ("mdi6.language-go",        "#00ADD8"),

    # ── PHP / Ruby / Swift / Dart ──
    ".php":   ("mdi6.language-php",       "#777BB4"),
    ".rb":    ("mdi6.language-ruby",      "#CC342D"),
    ".swift": ("mdi6.language-swift",     "#F05138"),
    ".dart":  ("mdi6.language-dart",      "#00B4AB"),

    # ── Shell / 脚本 ──
    ".sh":    ("mdi6.console",            "#89DCEB"),
    ".bash":  ("mdi6.console",            "#89DCEB"),
    ".zsh":   ("mdi6.console",            "#89DCEB"),
    ".fish":  ("mdi6.console",            "#89DCEB"),
    ".bat":   ("mdi6.console",            "#C1F12E"),
    ".ps1":   ("mdi6.powershell",         "#5391FE"),

    # ── 数据 / 配置 ──
    ".json":  ("mdi6.code-json",          "#CBCB41"),
    ".jsonc": ("mdi6.code-json",          "#CBCB41"),
    ".xml":   ("mdi6.xml",                "#E37933"),
    ".yml":   ("mdi6.cog",                "#6D8086"),
    ".yaml":  ("mdi6.cog",                "#6D8086"),
    ".toml":  ("mdi6.cog",                "#9C4221"),
    ".ini":   ("mdi6.cog",                "#6c7086"),
    ".cfg":   ("mdi6.cog",                "#6c7086"),
    ".conf":  ("mdi6.cog",                "#6c7086"),
    ".env":   ("mdi6.cog",                "#ECD53F"),
    ".properties": ("mdi6.cog",           "#6c7086"),

    # ── SQL / 数据库 ──
    ".sql":   ("mdi6.database",           "#e38c00"),
    ".db":    ("mdi6.database",           "#e38c00"),
    ".sqlite":("mdi6.database",           "#e38c00"),

    # ── 文档 ──
    ".md":    ("mdi6.language-markdown",  "#519ABA"),
    ".mdx":   ("mdi6.language-markdown",  "#519ABA"),
    ".rst":   ("mdi6.text-box-outline",   "#8DA9C4"),
    ".txt":   ("mdi6.text-box-outline",   "#A6ADC8"),
    ".pdf":   ("mdi6.file-pdf-box",       "#F40F02"),
    ".doc":   ("mdi6.file-word",          "#2B579A"),
    ".docx":  ("mdi6.file-word",          "#2B579A"),
    ".xls":   ("mdi6.file-excel",         "#217346"),
    ".xlsx":  ("mdi6.file-excel",         "#217346"),
    ".csv":   ("mdi6.file-delimited",     "#89dceb"),
    ".ppt":   ("mdi6.file-powerpoint",    "#D24726"),
    ".pptx":  ("mdi6.file-powerpoint",    "#D24726"),

    # ── 图片 ──
    ".png":   ("mdi6.file-image",         "#A074C4"),
    ".jpg":   ("mdi6.file-image",         "#A074C4"),
    ".jpeg":  ("mdi6.file-image",         "#A074C4"),
    ".gif":   ("mdi6.file-image",         "#A074C4"),
    ".webp":  ("mdi6.file-image",         "#A074C4"),
    ".ico":   ("mdi6.file-image",         "#A074C4"),
    ".bmp":   ("mdi6.file-image",         "#A074C4"),
    ".tiff":  ("mdi6.file-image",         "#A074C4"),
    ".tif":   ("mdi6.file-image",         "#A074C4"),

    # ── 音频 / 视频 ──
    ".mp3":   ("mdi6.music",              "#EE82EE"),
    ".wav":   ("mdi6.music",              "#EE82EE"),
    ".ogg":   ("mdi6.music",              "#EE82EE"),
    ".flac":  ("mdi6.music",              "#EE82EE"),
    ".mp4":   ("mdi6.video",              "#89DCEB"),
    ".mov":   ("mdi6.video",              "#89DCEB"),
    ".avi":   ("mdi6.video",              "#89DCEB"),
    ".mkv":   ("mdi6.video",              "#89DCEB"),

    # ── 压缩包 ──
    ".zip":   ("mdi6.zip-box",            "#F9E2AF"),
    ".tar":   ("mdi6.zip-box",            "#F9E2AF"),
    ".gz":    ("mdi6.zip-box",            "#F9E2AF"),
    ".bz2":   ("mdi6.zip-box",            "#F9E2AF"),
    ".xz":    ("mdi6.zip-box",            "#F9E2AF"),
    ".rar":   ("mdi6.zip-box",            "#F9E2AF"),
    ".7z":    ("mdi6.zip-box",            "#F9E2AF"),

    # ── Docker / CI ──
    ".dockerfile": ("mdi6.docker",        "#2496ED"),
    ".dockerignore": ("mdi6.docker",      "#2496ED"),

    # ── Git ──
    ".gitignore":   ("mdi6.git",          "#F14E32"),
    ".gitattributes":("mdi6.git",         "#F14E32"),
}

# 特殊无后缀文件名映射
_FILENAME_MAP: dict[str, tuple[str, str]] = {
    "dockerfile":      ("mdi6.docker",         "#2496ED"),
    ".dockerignore":   ("mdi6.docker",         "#2496ED"),
    "makefile":        ("mdi6.cog-outline",     "#6D8086"),
    "rakefile":        ("mdi6.language-ruby",   "#CC342D"),
    "gemfile":         ("mdi6.language-ruby",   "#CC342D"),
    "podfile":         ("mdi6.language-swift",  "#F05138"),
    ".gitignore":      ("mdi6.git",             "#F14E32"),
    ".gitattributes":  ("mdi6.git",             "#F14E32"),
    ".editorconfig":   ("mdi6.cog-outline",     "#6D8086"),
    ".eslintrc":       ("mdi6.eslint",          "#4B32C3"),
    ".prettierrc":     ("mdi6.code-braces",     "#F7B93E"),
    "package.json":    ("mdi6.nodejs",          "#68A063"),
    "tsconfig.json":   ("mdi6.language-typescript", "#3178C6"),
    "requirements.txt":("mdi6.language-python", "#3572A5"),
    "pipfile":         ("mdi6.language-python", "#3572A5"),
    "setup.py":        ("mdi6.language-python", "#3572A5"),
    "pyproject.toml":  ("mdi6.language-python", "#3572A5"),
}

# 默认文件图标
_DEFAULT_FILE  = ("mdi6.file-outline",   "#A6ADC8")
# 目录图标（折叠 / 展开）
_DIR_CLOSED    = ("mdi6.folder",         "#89B4FA")
_DIR_OPEN      = ("mdi6.folder-open",    "#89B4FA")


# ── 公共 API ─────────────────────────────────────────────────────────────

ICON_SIZE = QSize(16, 16)


@lru_cache(maxsize=256)
def get_file_icon(ext_or_name: str, is_dir: bool = False,
                  expanded: bool = False) -> QIcon:
    """
    返回对应的 QIcon。
    :param ext_or_name: 文件扩展名（含点，如 '.py'）或完整文件名（小写）
    :param is_dir:      是否目录
    :param expanded:    目录是否展开
    """
    if not _QTA_AVAILABLE:
        return QIcon()

    if is_dir:
        name, color = _DIR_OPEN if expanded else _DIR_CLOSED
    else:
        # 先查完整文件名，再查后缀
        key = ext_or_name.lower()
        name, color = (
            _FILENAME_MAP.get(key)
            or _EXT_MAP.get(key)
            or _DEFAULT_FILE
        )

    try:
        return qta.icon(name, color=color)
    except Exception:
        # 图标名不存在时降级
        try:
            fallback = "mdi6.file-outline" if not is_dir else "mdi6.folder"
            return qta.icon(fallback, color=color)
        except Exception:
            return QIcon()


def get_file_color(ext_or_name: str, is_dir: bool = False) -> str:
    """返回图标对应的颜色十六进制值，可用于文件名着色。"""
    if is_dir:
        return _DIR_CLOSED[1]
    key = ext_or_name.lower()
    _, color = (
        _FILENAME_MAP.get(key)
        or _EXT_MAP.get(key)
        or _DEFAULT_FILE
    )
    return color


def is_qtawesome_available() -> bool:
    return _QTA_AVAILABLE


# ── UI 操作图标（工具栏 / 按钮 / 菜单）────────────────────────────────────
# key → (mdi6 图标名, 颜色)
_UI_ICON_MAP: dict[str, tuple[str, str]] = {
    # 工具栏核心操作
    "update":      ("mdi6.arrow-down-circle",        "#89b4fa"),
    "commit":      ("mdi6.arrow-up-circle",          "#a6e3a1"),
    "revert":      ("mdi6.undo-variant",             "#f38ba8"),
    "add":         ("mdi6.plus-circle-outline",      "#89dceb"),
    "delete":      ("mdi6.minus-circle-outline",     "#f38ba8"),
    "lock":        ("mdi6.lock-outline",             "#f9e2af"),
    "unlock":      ("mdi6.lock-open-outline",        "#a6adc8"),
    "refresh":     ("mdi6.refresh",                  "#a6adc8"),
    "cleanup":     ("mdi6.broom",                    "#cba6f7"),
    "switch":      ("mdi6.source-branch",            "#cba6f7"),
    # 查看类
    "log":         ("mdi6.history",                  "#89b4fa"),
    "diff":        ("mdi6.compare-horizontal",       "#89dceb"),
    "blame":       ("mdi6.account-clock-outline",    "#a6adc8"),
    "properties":  ("mdi6.information-outline",      "#a6adc8"),
    # 仓库管理
    "add_repo":    ("mdi6.folder-plus-outline",      "#a6e3a1"),
    "checkout":    ("mdi6.download-outline",         "#89b4fa"),
    "remove_repo": ("mdi6.folder-remove-outline",    "#f38ba8"),
    "rename":      ("mdi6.rename-box-outline",       "#f9e2af"),
    "preferences": ("mdi6.cog-outline",              "#a6adc8"),
    # 文件操作
    "open_finder": ("mdi6.folder-eye-outline",       "#89b4fa"),
    # 侧边栏 / 欢迎页
    "welcome":     ("mdi6.source-branch-check",      "#89b4fa"),
    "repo_item":   ("mdi6.source-repository",        "#89b4fa"),
    # 冲突解决
    "conflict":        ("mdi6.alert-circle-outline",     "#f38ba8"),
    "accept_mine":     ("mdi6.account-check-outline",    "#a6e3a1"),
    "accept_theirs":   ("mdi6.cloud-download-outline",   "#89b4fa"),
    "accept_working":  ("mdi6.file-check-outline",       "#f9e2af"),
}


@lru_cache(maxsize=128)
def get_ui_icon(key: str, color: str = "") -> QIcon:
    """
    返回 UI 操作图标（工具栏、按钮、菜单项）。
    :param key:   操作名，参见 _UI_ICON_MAP
    :param color: 可选，覆盖默认颜色（十六进制）
    """
    if not _QTA_AVAILABLE:
        return QIcon()
    icon_name, default_color = _UI_ICON_MAP.get(key, ("mdi6.help-circle-outline", "#a6adc8"))
    final_color = color if color else default_color
    try:
        return qta.icon(icon_name, color=final_color)
    except Exception:
        return QIcon()
