import iconManifest from "../assets/material-icon-map.json";

type IconManifest = {
  file: string;
  folder: string;
  folderExpanded?: string;
  fileNames?: Record<string, string>;
  fileExtensions?: Record<string, string>;
  folderNames?: Record<string, string>;
  folderNamesExpanded?: Record<string, string>;
};

const manifest = iconManifest as IconManifest;

const ICON_BASE = `${import.meta.env.BASE_URL}material-icons`;

const defaultFileName = manifest.file || "file";
const defaultFolderName = manifest.folder || "folder";
const defaultFolderOpenName = manifest.folderExpanded || "folder-open";

function iconUrl(iconName: string): string {
  return `${ICON_BASE}/${iconName}.svg`;
}

function resolveIconName(iconName: string | undefined | null, fallback: string): string {
  return iconName || fallback;
}

function matchFileExtension(fileNameLower: string): string | undefined {
  const extensions = manifest.fileExtensions || {};
  const parts = fileNameLower.split(".");
  if (parts.length < 2) return undefined;

  // Prefer longer compound extensions: "d.ts", "spec.ts", etc.
  for (let i = 1; i < parts.length; i += 1) {
    const ext = parts.slice(i).join(".");
    if (extensions[ext]) return extensions[ext];
  }
  return undefined;
}

export function getMaterialIconUrl(
  name: string,
  isDir: boolean,
  options?: { expanded?: boolean },
): string {
  const lower = (name || "").toLowerCase();

  if (isDir) {
    const expanded = Boolean(options?.expanded);
    const folderNames = expanded ? manifest.folderNamesExpanded : manifest.folderNames;
    const fallback = expanded ? defaultFolderOpenName : defaultFolderName;
    const iconName = resolveIconName(folderNames?.[lower], fallback);
    return iconUrl(iconName);
  }

  const fileNames = manifest.fileNames || {};
  if (fileNames[lower]) return iconUrl(fileNames[lower]);

  const byExt = matchFileExtension(lower);
  if (byExt) return iconUrl(byExt);

  return iconUrl(defaultFileName);
}

export type SvnStatusMeta = {
  code: string;
  label: string;
  className: string;
};

/** Normalize multi-char statuses (e.g. "M ", "A+") to a primary badge code. */
export function getSvnStatusMeta(status?: string | null): SvnStatusMeta | null {
  if (!status) return null;
  const raw = String(status).trim();
  if (!raw || raw === "—" || raw === "-") return null;

  // Prefer first meaningful SVN status mark.
  const match = raw.match(/[MADCRXI?!+~*]/);
  const code = (match?.[0] || raw[0]) as string;
  switch (code) {
    case "M":
      return { code: "M", label: "已修改", className: "M" };
    case "A":
      return { code: "A", label: "已添加", className: "A" };
    case "D":
      return { code: "D", label: "已删除", className: "D" };
    case "C":
      return { code: "C", label: "冲突", className: "C" };
    case "R":
      return { code: "R", label: "已替换", className: "R" };
    case "X":
      return { code: "X", label: "外部引用", className: "X" };
    case "I":
      return { code: "I", label: "已忽略", className: "I" };
    case "?":
      return { code: "?", label: "未纳入版本控制", className: "question" };
    case "!":
      return { code: "!", label: "缺失", className: "missing" };
    case "~":
      return { code: "~", label: "类型变更", className: "tilde" };
    case "+":
      return { code: "+", label: "历史有关联", className: "plus" };
    case "-":
      return { code: "-", label: "已移除", className: "minus" };
    default:
      return { code, label: `状态 ${raw}`, className: "other" };
  }
}

/** 未纳入版本控制 / 忽略 / 外部引用等不可还原 */
export function canRevertSvnStatus(status?: string | null): boolean {
  const meta = getSvnStatusMeta(status);
  if (!meta) return false;
  // ? 未版本控制、I 忽略、X 外部引用：没有版本库基线可还原
  if (meta.code === "?" || meta.code === "I" || meta.code === "X") return false;
  return ["M", "A", "D", "R", "C", "!", "~"].includes(meta.code);
}

