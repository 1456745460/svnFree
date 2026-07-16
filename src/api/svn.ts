import { invoke } from "@tauri-apps/api/core";
import type {
  CommandResult,
  DiffFileContent,
  DiffFileInfo,
  FsEntry,
  PreviewPayload,
  SvnLogEntry,
  SvnStatusItem,
  Workspace,
} from "../types";

export function listWorkspaces() {
  return invoke<Workspace[]>("list_workspaces");
}

export function addWorkspace(path: string, name?: string) {
  return invoke<Workspace>("add_workspace", { path, name });
}

export function removeWorkspace(id: string) {
  return invoke<void>("remove_workspace", { id });
}

export function renameWorkspace(id: string, name: string) {
  return invoke<Workspace>("rename_workspace", { id, name });
}

export function checkoutWorkspace(
  url: string,
  path: string,
  name: string | undefined,
  jobId: string,
) {
  return invoke<void>("checkout_workspace", { url, path, name, jobId });
}

export function listDirectory(path: string) {
  return invoke<FsEntry[]>("list_directory", { path });
}

export function svnUpdate(path: string, jobId: string) {
  return invoke<void>("svn_update", { path, jobId });
}

export function svnCommit(path: string, message: string, paths?: string[]) {
  return invoke<CommandResult>("svn_commit", { path, message, paths: paths || null });
}

export function svnStatus(path: string, recursive = true) {
  return invoke<SvnStatusItem[]>("svn_status", { path, recursive });
}

export function svnStatusMany(paths: string[], recursive = true) {
  return invoke<SvnStatusItem[]>("svn_status_many", { paths, recursive });
}

export function svnAdd(paths: string[]) {
  return invoke<CommandResult>("svn_add", { paths });
}

export function svnIgnore(path: string) {
  return invoke<CommandResult>("svn_ignore", { path });
}

export function svnResolved(path: string) {
  return invoke<CommandResult>("svn_resolved", { path });
}

export function svnLock(paths: string[], message?: string) {
  return invoke<CommandResult>("svn_lock", { paths, message: message || null });
}

export function svnUnlock(paths: string[]) {
  return invoke<CommandResult>("svn_unlock", { paths });
}

export function svnSwitch(path: string, url: string) {
  return invoke<CommandResult>("svn_switch", { path, url });
}

export function svnBlame(path: string) {
  return invoke<CommandResult>("svn_blame", { path });
}

export function svnPatch(path: string) {
  return invoke<CommandResult>("svn_patch", { path });
}

export function svnRevert(path: string) {
  return invoke<CommandResult>("svn_revert", { path });
}

export function localDelete(path: string) {
  return invoke<CommandResult>("local_delete", { path });
}

export function svnDelete(path: string, force = true) {
  return invoke<CommandResult>("svn_delete", { path, force });
}

export function svnClean(path: string) {
  return invoke<CommandResult>("svn_clean", { path });
}

export function svnRename(path: string, newName: string) {
  return invoke<CommandResult>("svn_rename", { path, newName });
}

export function svnDiff(path: string) {
  return invoke<CommandResult>("svn_diff", { path });
}

export function svnDiffFiles(path: string) {
  return invoke<DiffFileInfo[]>("svn_diff_files", { path });
}

export function svnDiffFileContent(path: string) {
  return invoke<DiffFileContent>("svn_diff_file_content", { path });
}

export function svnLog(path: string, limit = 30) {
  return invoke<CommandResult>("svn_log", { path, limit });
}

export function svnLogEntries(path: string, limit = 30) {
  return invoke<SvnLogEntry[]>("svn_log_entries", { path, limit });
}

export function svnRevisionDiffFileContent(path: string, revision: string, action?: string | null) {
  return invoke<DiffFileContent>("svn_revision_diff_file_content", { path, revision, action: action || null });
}

export function svnProplist(path: string) {
  return invoke<CommandResult>("svn_proplist", { path });
}

export function svnInfo(path: string) {
  return invoke<CommandResult>("svn_info", { path });
}

export function revealInFinder(path: string) {
  return invoke<void>("reveal_in_finder", { path });
}

export function previewFile(path: string) {
  return invoke<PreviewPayload>("preview_file", { path });
}

export function isSvnWorkingCopy(path: string) {
  return invoke<boolean>("is_svn_working_copy", { path });
}
