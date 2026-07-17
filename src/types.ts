export interface Workspace {
  id: string;
  name: string;
  path: string;
  url?: string | null;
  createdAt: string;
}

export interface FsEntry {
  name: string;
  path: string;
  isDir: boolean;
  size: number;
  modified?: number | null;
  extension?: string | null;
  svnStatus?: string | null;
}

export interface CommandResult {
  success: boolean;
  stdout: string;
  stderr: string;
  code?: number | null;
}

export interface PreviewPayload {
  kind: "text" | "image" | "directory" | "binary" | "large" | string;
  path: string;
  name: string;
  size: number;
  mime?: string | null;
  content?: string | null;
  dataUrl?: string | null;
  message?: string | null;
}

export interface SvnProgressEvent {
  jobId: string;
  phase: "start" | "log" | "done" | "error" | string;
  line?: string | null;
  stream?: "stdout" | "stderr" | string | null;
  success?: boolean | null;
  code?: number | null;
  message?: string | null;
}

export interface SvnStatusItem {
  path: string;
  name: string;
  status: string;
  isDir: boolean;
  relativePath: string;
}

export interface SvnLogPath {
  path: string;
  action: string;
  kind?: string | null;
  copyFromPath?: string | null;
  copyFromRevision?: string | null;
}

export interface SvnLogEntry {
  revision: string;
  author?: string | null;
  date?: string | null;
  message: string;
  paths: SvnLogPath[];
}

export type ViewMode = "list" | "icons" | "columns";

/** 中间文件列表右键 */
export type ContextAction =
  | "update"
  | "commit"
  | "add"
  | "ignore"
  | "diff"
  | "log"
  | "info"
  | "proplist"
  | "resolved"
  | "blame"
  | "lock"
  | "unlock"
  | "patch"
  | "revert"
  | "reveal"
  | "clean"
  | "rename"
  | "localDelete"
  | "svnDelete";

/** 左侧工作副本右键 */
export type WorkspaceAction =
  | "update"
  | "commit"
  | "diff"
  | "log"
  | "info"
  | "switch"
  | "patch"
  | "revert"
  | "reveal"
  | "clean"
  | "rename"
  | "remove";

export type ModalType =
  | "checkout"
  | "commit"
  | "output"
  | "rename"
  | "switch"
  | "changes"
  | null;

export interface ContextMenuState {
  visible: boolean;
  x: number;
  y: number;
  mode: "file" | "workspace";
  entry: FsEntry | null;
  workspace: Workspace | null;
}

export interface ToastMessage {
  id: number;
  type: "info" | "success" | "error";
  text: string;
}

export interface ProgressState {
  visible: boolean;
  title: string;
  running: boolean;
  success: boolean | null;
  lines: string[];
  status: string;
  jobId: string | null;
}

export interface DiffFileInfo {
  path: string;
  relativePath: string;
  name: string;
  status: string;
  statusLabel: string;
  binary: boolean;
  isDir: boolean;
  additions?: number;
  deletions?: number;
}

/** 来自 svn diff 文本解析的 +/- 行统计（无需 cat） */
export interface DiffFileStat {
  path: string;
  relativePath: string;
  name: string;
  additions: number;
  deletions: number;
  binary: boolean;
}

export interface DiffFileContent {
  path: string;
  relativePath: string;
  name: string;
  status: string;
  statusLabel: string;
  binary: boolean;
  oldText: string;
  newText: string;
  oldExists: boolean;
  newExists: boolean;
  language: string;
  message?: string | null;
}

export type DiffViewMode = "split" | "unified";

export interface DiffViewerState {
  rootPath: string;
  title: string;
}
