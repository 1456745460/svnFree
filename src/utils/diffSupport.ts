/** 明确无法做文本 Diff 的扩展名（图片/Office/压缩包/编译产物等） */
const UNSUPPORTED_EXTENSIONS = new Set([
  // images
  "png",
  "jpg",
  "jpeg",
  "gif",
  "webp",
  "bmp",
  "ico",
  "tif",
  "tiff",
  "heic",
  "heif",
  "avif",
  // office / docs
  "pdf",
  "doc",
  "docx",
  "xls",
  "xlsx",
  "xlsm",
  "ppt",
  "pptx",
  "pages",
  "numbers",
  "key",
  // archives / packages
  "zip",
  "rar",
  "7z",
  "tar",
  "gz",
  "tgz",
  "bz2",
  "xz",
  "jar",
  "war",
  "ear",
  "apk",
  "dmg",
  "iso",
  // compiled / binary
  "class",
  "o",
  "a",
  "so",
  "dll",
  "dylib",
  "exe",
  "bin",
  "dat",
  "db",
  "sqlite",
  "sqlite3",
  // fonts / media
  "ttf",
  "otf",
  "woff",
  "woff2",
  "eot",
  "mp3",
  "mp4",
  "wav",
  "flac",
  "aac",
  "ogg",
  "avi",
  "mov",
  "mkv",
  "webm",
  // design
  "psd",
  "ai",
  "sketch",
  "fig",
  "xd",
]);

const UNSUPPORTED_BASENAMES = new Set([".ds_store", "thumbs.db", "desktop.ini"]);

function fileNameOf(path: string): string {
  const clean = (path || "").replace(/\\/g, "/");
  const parts = clean.split("/").filter(Boolean);
  return parts[parts.length - 1] || clean;
}

function extensionOf(fileName: string): string {
  const lower = fileName.toLowerCase();
  const dot = lower.lastIndexOf(".");
  if (dot <= 0 || dot === lower.length - 1) return "";
  return lower.slice(dot + 1);
}

/**
 * 是否不适合进入 Diff 变更列表（目录 / 已标记二进制 / 明确二进制扩展名）。
 * 真正内容是二进制但扩展名看起来像文本的，会在加载内容后被剔除。
 */
export function isUnsupportedDiffPath(
  path: string,
  options?: { isDir?: boolean | null; binary?: boolean | null; kind?: string | null },
): boolean {
  if (options?.isDir) return true;
  if (options?.binary) return true;
  if ((options?.kind || "").toLowerCase() === "dir") return true;

  const name = fileNameOf(path);
  if (!name) return true;
  if (UNSUPPORTED_BASENAMES.has(name.toLowerCase())) return true;

  const ext = extensionOf(name);
  if (ext && UNSUPPORTED_EXTENSIONS.has(ext)) return true;
  return false;
}

export function filterDiffableFiles<T extends { path: string; isDir?: boolean; binary?: boolean; kind?: string | null }>(
  items: T[],
): T[] {
  return items.filter(
    (item) =>
      !isUnsupportedDiffPath(item.path, {
        isDir: item.isDir,
        binary: item.binary,
        kind: item.kind,
      }),
  );
}
