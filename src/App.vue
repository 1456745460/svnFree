<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref } from "vue";
import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { getCurrentWindow } from "@tauri-apps/api/window";
import { confirm as nativeConfirm, open } from "@tauri-apps/plugin-dialog";
import Sidebar from "./components/Sidebar.vue";
import FileExplorer from "./components/FileExplorer.vue";
import PreviewPanel from "./components/PreviewPanel.vue";
import ContextMenu from "./components/ContextMenu.vue";
import Modals from "./components/Modals.vue";
import DiffViewer from "./components/DiffViewer.vue";
import * as api from "./api/svn";
import type { ContextAction, ContextMenuState, DiffFileInfo, FsEntry, PreviewPayload, ProgressState, SvnLogEntry, SvnProgressEvent, SvnStatusItem, ToastMessage, ViewMode, Workspace, WorkspaceAction, SvnLogPath } from "./types";
import { canRevertSvnStatus, getSvnStatusMeta } from "./utils/materialIcon";
import { isUnsupportedDiffPath } from "./utils/diffSupport";

const workspaces = ref<Workspace[]>([]);
const activeId = ref<string | null>(null);
const currentPath = ref<string>("");
const entries = ref<FsEntry[]>([]);
const selectedEntry = ref<FsEntry | null>(null);
const selectedPaths = ref<string[]>([]);
const selectionAnchorPath = ref<string | null>(null);
const preview = ref<PreviewPayload | null>(null);
const viewMode = ref<ViewMode>("columns");
const busy = ref(false);
const previewBusy = ref(false);

const SIDEBAR_MIN = 180;
const SIDEBAR_MAX = 480;
const PREVIEW_MIN = 240;
const PREVIEW_MAX = 720;
const PREVIEW_COLLAPSED_WIDTH = 42;
const CENTER_MIN = 320;
const RESIZER_WIDTH = 6;

function readLayoutPref(key: string, fallback: string) {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

function writeLayoutPref(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // ignore
  }
}

function clamp(n: number, min: number, max: number) {
  return Math.min(max, Math.max(min, n));
}

const sidebarWidth = ref(clamp(Number(readLayoutPref("sf.layout.sidebarWidth", "250")) || 250, SIDEBAR_MIN, SIDEBAR_MAX));
const previewWidth = ref(clamp(Number(readLayoutPref("sf.layout.previewWidth", "340")) || 340, PREVIEW_MIN, PREVIEW_MAX));
const previewCollapsed = ref(readLayoutPref("sf.layout.previewCollapsed", "1") !== "0");

const shellStyle = computed(() => {
  const right = previewCollapsed.value ? PREVIEW_COLLAPSED_WIDTH : previewWidth.value;
  return {
    "--sidebar-width": `${sidebarWidth.value}px`,
    "--preview-width": `${right}px`,
    "--resizer-width": `${RESIZER_WIDTH}px`,
  } as Record<string, string>;
});

function persistLayoutPrefs() {
  writeLayoutPref("sf.layout.sidebarWidth", String(sidebarWidth.value));
  writeLayoutPref("sf.layout.previewWidth", String(previewWidth.value));
  writeLayoutPref("sf.layout.previewCollapsed", previewCollapsed.value ? "1" : "0");
}

function togglePreviewCollapsed() {
  previewCollapsed.value = !previewCollapsed.value;
  persistLayoutPrefs();
}

function onSidebarResizeStart(e: MouseEvent) {
  if (e.button !== 0) return;
  e.preventDefault();
  const startX = e.clientX;
  const startW = sidebarWidth.value;
  document.body.classList.add("is-resizing-layout");

  const onMove = (ev: MouseEvent) => {
    const shell = document.querySelector(".app-shell") as HTMLElement | null;
    const total = shell?.clientWidth || window.innerWidth;
    const right = previewCollapsed.value ? PREVIEW_COLLAPSED_WIDTH : previewWidth.value;
    const maxByCenter = total - right - RESIZER_WIDTH * 2 - CENTER_MIN;
    const max = Math.max(SIDEBAR_MIN, Math.min(SIDEBAR_MAX, maxByCenter));
    sidebarWidth.value = clamp(startW + (ev.clientX - startX), SIDEBAR_MIN, max);
  };

  const onUp = () => {
    document.body.classList.remove("is-resizing-layout");
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("mouseup", onUp);
    persistLayoutPrefs();
  };

  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);
}

function onPreviewResizeStart(e: MouseEvent) {
  if (e.button !== 0 || previewCollapsed.value) return;
  e.preventDefault();
  const startX = e.clientX;
  const startW = previewWidth.value;
  document.body.classList.add("is-resizing-layout");

  const onMove = (ev: MouseEvent) => {
    const shell = document.querySelector(".app-shell") as HTMLElement | null;
    const total = shell?.clientWidth || window.innerWidth;
    const maxByCenter = total - sidebarWidth.value - RESIZER_WIDTH * 2 - CENTER_MIN;
    const max = Math.max(PREVIEW_MIN, Math.min(PREVIEW_MAX, maxByCenter));
    // 拖左边分割线：向右拖应变窄
    previewWidth.value = clamp(startW - (ev.clientX - startX), PREVIEW_MIN, max);
  };

  const onUp = () => {
    document.body.classList.remove("is-resizing-layout");
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("mouseup", onUp);
    persistLayoutPrefs();
  };

  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);
}

const statusText = ref("就绪");
const toasts = ref<ToastMessage[]>([]);
let toastSeq = 1;

const modalType = ref<"checkout" | "commit" | "output" | "rename" | "switch" | "changes" | "history" | null>(null);
const modalTitle = ref("");
const modalOutput = ref("");
const diffViewerOpen = ref(false);
const diffViewerPath = ref("");
const diffViewerTitle = ref("DIFF");
const diffViewerRevision = ref<string | null>(null);
const diffViewerFiles = ref<DiffFileInfo[] | null>(null);
const diffViewerFocusPath = ref<string | null>(null);
const commitTarget = ref<string>("");
const commitItems = ref<SvnStatusItem[]>([]);
const commitLoading = ref(false);
const switchTarget = ref<string>("");
const changesRoot = ref<string>("");
const changesItems = ref<SvnStatusItem[]>([]);
const changesLoading = ref(false);
const renameTarget = ref<string>("");
const renameFromName = ref<string>("");
const renameWorkspaceId = ref<string>("");
const renameKind = ref<"file" | "workspace">("file");
const columnStacks = ref<{ path: string; entries: FsEntry[]; selected?: string | null }[]>([]);
const historyRoot = ref("");
const historyItems = ref<SvnLogEntry[]>([]);
const historyLoading = ref(false);
const historySelectedRevision = ref<string>("");
const historySelectedAction = ref<string>("");
const historyWcLocal = ref("");
const historyRepoPrefix = ref("");

const contextMenu = ref<ContextMenuState>({
  visible: false,
  x: 0,
  y: 0,
  mode: "file",
  entry: null,
  workspace: null,
});

const progress = ref<ProgressState>({
  visible: false,
  title: "",
  running: false,
  success: null,
  lines: [],
  status: "",
  jobId: null,
});

let progressUnlisten: UnlistenFn | null = null;
let jobSeq = 1;

function newJobId(prefix: string) {
  return `${prefix}-${Date.now()}-${jobSeq++}`;
}

function openProgress(title: string, jobId: string) {
  progress.value = {
    visible: true,
    title,
    running: true,
    success: null,
    lines: [],
    status: "准备执行...",
    jobId,
  };
}

function sanitizeLogLine(line: string) {
  // 过滤伪终端控制字符（如 script 的 ^D）与不可见控制符
  return line
    .replace(/\u0004/g, "")
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F]/g, "")
    .replace(/\^D/g, "")
    .trimEnd();
}

function appendProgressLine(line: string) {
  const cleaned = sanitizeLogLine(line);
  if (!cleaned.trim()) return;
  progress.value.lines.push(cleaned);
  // 防止日志无限膨胀
  if (progress.value.lines.length > 4000) {
    progress.value.lines = progress.value.lines.slice(-3000);
  }
}

function finishProgress(success: boolean, status: string) {
  progress.value.running = false;
  progress.value.success = success;
  progress.value.status = status;
}

function closeProgress() {
  if (progress.value.running) return;
  progress.value.visible = false;
}

function currentJobKind(): "checkout" | "update" | "other" {
  const id = progress.value.jobId || "";
  if (id.startsWith("checkout-")) return "checkout";
  if (id.startsWith("update-")) return "update";
  return "other";
}

async function onJobFinished(success: boolean, message: string) {
  const kind = currentJobKind();
  if (kind === "checkout") {
    if (success) {
      try {
        await refreshWorkspaces();
        // 尝试选中最近添加的工作副本
        const list = workspaces.value;
        if (list.length) {
          const latest = list[list.length - 1];
          await loadDir(latest.path);
        }
        toast(message || "检出完成", "success");
        statusText.value = "就绪";
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        toast(msg, "error");
        statusText.value = `错误: ${msg}`;
      }
    } else {
      toast(message || "检出失败", "error");
      statusText.value = `错误: ${message || "检出失败"}`;
    }
    return;
  }

  if (kind === "update") {
    if (success) {
      try {
        await refreshCurrent();
        toast(message || "更新完成", "success");
        statusText.value = "就绪";
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        toast(msg, "error");
        statusText.value = `错误: ${msg}`;
      }
    } else {
      toast(message || "更新失败", "error");
      statusText.value = `错误: ${message || "更新失败"}`;
    }
  }
}

function handleProgressEvent(event: SvnProgressEvent) {
  if (!progress.value.jobId || event.jobId !== progress.value.jobId) return;

  if (event.phase === "start") {
    progress.value.status = event.message || "开始执行...";
    if (event.message) {
      for (const part of event.message.split("\n")) {
        if (part.trim()) appendProgressLine(part);
      }
    }
    return;
  }

  if (event.phase === "log") {
    const raw = event.line || "";
    if (!raw) return;
    const prefix = event.stream === "stderr" ? "[stderr] " : "";
    appendProgressLine(prefix + raw);
    // 用最新有效行作为状态摘要
    progress.value.status = raw.length > 80 ? raw.slice(0, 80) + "…" : raw;
    return;
  }

  if (event.phase === "done") {
    const msg = event.message || (event.success ? "操作完成" : "操作结束");
    finishProgress(Boolean(event.success), msg);
    if (event.message) appendProgressLine(event.message);
    void onJobFinished(Boolean(event.success), msg);
    return;
  }

  if (event.phase === "error") {
    const msg = event.message || event.line || "操作失败";
    // 忽略无意义空错误（如 null/undefined 转字符串）
    if (!msg || msg === "null" || msg === "undefined") return;
    // 若进度已结束则忽略重复 error（async 兜底可能二次触发）
    if (!progress.value.running) return;
    finishProgress(false, msg);
    if (event.line || event.message) {
      appendProgressLine(`[stderr] ${event.line || event.message}`);
    }
    void onJobFinished(false, msg);
  }
}

const activeWorkspace = computed(
  () => workspaces.value.find((w) => w.id === activeId.value) || null,
);

const breadcrumb = computed(() => {
  const ws = activeWorkspace.value;
  if (!ws || !currentPath.value) return [];
  const root = normalize(ws.path);
  const cur = normalize(currentPath.value);
  const items: { label: string; path: string }[] = [{ label: ws.name, path: root }];
  if (cur === root) return items;
  if (!cur.startsWith(root + "/") && cur !== root) return [{ label: cur, path: cur }];
  const rest = cur.slice(root.length).replace(/^\/+/, "");
  let acc = root;
  for (const part of rest.split("/").filter(Boolean)) {
    acc = `${acc}/${part}`;
    items.push({ label: part, path: acc });
  }
  return items;
});

function normalize(p: string) {
  return p.replace(/\/+$/, "");
}

function toast(text: string, type: ToastMessage["type"] = "info") {
  const id = toastSeq++;
  toasts.value.push({ id, text, type });
  setTimeout(() => {
    toasts.value = toasts.value.filter((t) => t.id !== id);
  }, 3200);
}

async function withBusy<T>(fn: () => Promise<T>, label = "处理中..."): Promise<T | null> {
  if (busy.value) return null;
  busy.value = true;
  statusText.value = label;
  try {
    return await fn();
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    toast(msg, "error");
    statusText.value = `错误: ${msg}`;
    return null;
  } finally {
    busy.value = false;
    if (!statusText.value.startsWith("错误")) {
      statusText.value = "就绪";
    }
  }
}

function breadcrumbPaths(path: string) {
  const ws = activeWorkspace.value;
  if (!ws) return [normalize(path)];
  const root = normalize(ws.path);
  const cur = normalize(path);
  const paths = [root];
  if (cur === root) return paths;
  const rest = cur.startsWith(root + "/") ? cur.slice(root.length + 1) : "";
  let acc = root;
  for (const part of rest.split("/").filter(Boolean)) {
    acc = `${acc}/${part}`;
    paths.push(acc);
  }
  return paths;
}

async function rebuildColumns(path: string, selectedPath?: string | null) {
  const paths = breadcrumbPaths(path);
  const stacks: typeof columnStacks.value = [];
  for (let i = 0; i < paths.length; i++) {
    const p = paths[i];
    const ents = await api.listDirectory(p);
    stacks.push({
      path: p,
      entries: ents,
      selected: paths[i + 1] || selectedPath || null,
    });
  }
  columnStacks.value = stacks;
  entries.value = stacks[stacks.length - 1]?.entries || [];
}

async function refreshWorkspaces(preferId?: string | null) {
  const list = await api.listWorkspaces();
  workspaces.value = list;
  const next =
    (preferId && list.find((w) => w.id === preferId)?.id) ||
    (activeId.value && list.find((w) => w.id === activeId.value)?.id) ||
    list[0]?.id ||
    null;
  activeId.value = next;
  if (!next) {
    currentPath.value = "";
    entries.value = [];
    selectedEntry.value = null;
    selectedPaths.value = [];
    selectionAnchorPath.value = null;
    preview.value = null;
    columnStacks.value = [];
  }
}

async function loadDir(path: string) {
  const list = await api.listDirectory(path);
  currentPath.value = path;
  entries.value = list;
  const exist = new Set(list.map((e) => e.path));
  selectedPaths.value = selectedPaths.value.filter((p) => exist.has(p));
  if (selectedEntry.value && !exist.has(selectedEntry.value.path)) {
    selectedEntry.value = null;
  }
  if (selectedEntry.value && !selectedPaths.value.includes(selectedEntry.value.path)) {
    selectedPaths.value = [selectedEntry.value.path, ...selectedPaths.value];
  }
  if (!selectedPaths.value.length) {
    selectedEntry.value = null;
    selectionAnchorPath.value = null;
  } else if (!selectedEntry.value) {
    selectedEntry.value = list.find((e) => e.path === selectedPaths.value[0]) || null;
  }
  if (viewMode.value === "columns") {
    await rebuildColumns(path, selectedEntry.value?.path || null);
  } else {
    columnStacks.value = [];
  }
}

async function selectWorkspace(id: string) {
  activeId.value = id;
  const ws = workspaces.value.find((w) => w.id === id);
  if (!ws) return;
  selectedEntry.value = null;
  selectedPaths.value = [];
  selectionAnchorPath.value = null;
  preview.value = null;
  await withBusy(async () => {
    await loadDir(ws.path);
  }, "加载工作副本...");
}

async function onAddWorkspace() {
  const selected = await open({
    directory: true,
    multiple: false,
    title: "选择 SVN 工作副本文件夹",
  });
  if (!selected || Array.isArray(selected)) return;

  await withBusy(async () => {
    const isWc = await api.isSvnWorkingCopy(selected);
    if (!isWc) {
      throw new Error("所选目录不是 SVN 工作副本（缺少 .svn）");
    }
    const ws = await api.addWorkspace(selected);
    await refreshWorkspaces(ws.id);
    await loadDir(ws.path);
    toast(`已添加工作副本：${ws.name}`, "success");
  }, "添加工作副本...");
}

function openCheckoutModal() {
  modalType.value = "checkout";
}

async function onCheckout(payload: { url: string; path: string; name?: string }) {
  if (progress.value.running) {
    toast("已有任务进行中，请稍候", "info");
    return;
  }
  modalType.value = null;
  const jobId = newJobId("checkout");
  // 先立刻弹出进度窗，再启动后台任务，保证用户马上看到实时日志
  openProgress("检出进度", jobId);
  appendProgressLine("已创建检出任务，正在启动...");
  statusText.value = "正在检出...";
  await nextTick();
  try {
    await api.checkoutWorkspace(payload.url, payload.path, payload.name, jobId);
    // 命令立即返回；后续日志 / 完成态由 svn-progress 事件驱动
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    appendProgressLine(`[stderr] ${msg}`);
    finishProgress(false, msg);
    toast(msg, "error");
    statusText.value = `错误: ${msg}`;
  }
}

async function onRemoveWorkspace(id: string) {
  const ws = workspaces.value.find((w) => w.id === id);
  if (!ws) return;
  const ok = window.confirm(
    `从列表移除「${ws.name}」？\n不会删除本地文件：\n${ws.path}`,
  );
  if (!ok) return;
  await withBusy(async () => {
    await api.removeWorkspace(id);
    await refreshWorkspaces();
    if (activeId.value) {
      const cur = workspaces.value.find((w) => w.id === activeId.value);
      if (cur) await loadDir(cur.path);
    }
    toast("已移除工作副本（本地文件保留）", "success");
  }, "移除中...");
}

function resolveEntriesByPaths(paths: string[]) {
  const map = new Map(entries.value.map((e) => [e.path, e]));
  for (const col of columnStacks.value) {
    for (const e of col.entries) map.set(e.path, e);
  }
  return paths.map((p) => map.get(p)).filter((e): e is FsEntry => !!e);
}

function setSelection(paths: string[], primary?: FsEntry | null) {
  const uniq: string[] = [];
  const seen = new Set<string>();
  for (const p of paths) {
    if (!p || seen.has(p)) continue;
    seen.add(p);
    uniq.push(p);
  }
  selectedPaths.value = uniq;
  if (!uniq.length) {
    selectedEntry.value = null;
    selectionAnchorPath.value = null;
    preview.value = null;
    return;
  }
  const primaryPath =
    primary?.path && uniq.includes(primary.path) ? primary.path : uniq[uniq.length - 1];
  const resolved = resolveEntriesByPaths([primaryPath])[0] || primary || null;
  selectedEntry.value = resolved;
  if (!selectionAnchorPath.value || !uniq.includes(selectionAnchorPath.value)) {
    selectionAnchorPath.value = primaryPath;
  }
  void loadPreviewFor(resolved);
}

async function loadPreviewFor(entry: FsEntry | null) {
  if (!entry) {
    preview.value = null;
    return;
  }
  previewBusy.value = true;
  try {
    preview.value = await api.previewFile(entry.path);
  } catch (e) {
    preview.value = null;
    const msg = e instanceof Error ? e.message : String(e);
    toast(msg, "error");
  } finally {
    previewBusy.value = false;
  }
}

async function onSelectEntry(payload: { entry: FsEntry; additive: boolean; range: boolean }) {
  const { entry, additive, range } = payload;

  if (viewMode.value === "columns") {
    const idx = columnStacks.value.findIndex((c) =>
      c.entries.some((e) => e.path === entry.path),
    );
    if (idx >= 0) {
      columnStacks.value[idx].selected = entry.path;
      if (!additive && !range) {
        columnStacks.value = columnStacks.value.slice(0, idx + 1);
      }
    }
  }

  if (range && selectionAnchorPath.value) {
    const list =
      viewMode.value === "columns"
        ? (() => {
            const col = columnStacks.value.find((c) =>
              c.entries.some((e) => e.path === entry.path),
            );
            return col?.entries || entries.value;
          })()
        : entries.value;
    const a = list.findIndex((e) => e.path === selectionAnchorPath.value);
    const b = list.findIndex((e) => e.path === entry.path);
    if (a >= 0 && b >= 0) {
      const [lo, hi] = a < b ? [a, b] : [b, a];
      const rangePaths = list.slice(lo, hi + 1).map((e) => e.path);
      if (additive) {
        const set = new Set(selectedPaths.value);
        for (const p of rangePaths) set.add(p);
        setSelection(Array.from(set), entry);
      } else {
        setSelection(rangePaths, entry);
      }
      return;
    }
  }

  if (additive) {
    const set = new Set(selectedPaths.value);
    if (set.has(entry.path)) set.delete(entry.path);
    else set.add(entry.path);
    const next = Array.from(set);
    setSelection(next, set.has(entry.path) ? entry : null);
    selectionAnchorPath.value = entry.path;
    return;
  }

  setSelection([entry.path], entry);
  selectionAnchorPath.value = entry.path;
}

function onSelectPaths(paths: string[]) {
  if (!paths.length) {
    setSelection([]);
    return;
  }
  const primary = resolveEntriesByPaths([paths[paths.length - 1]])[0] || null;
  setSelection(paths, primary);
  selectionAnchorPath.value = paths[paths.length - 1] || null;
}

async function onOpenEntry(entry: FsEntry) {
  if (!entry.isDir) return;
  await withBusy(async () => {
    if (viewMode.value === "columns") {
      const parentIdx = columnStacks.value.findIndex((c) =>
        c.entries.some((e) => e.path === entry.path),
      );
      if (parentIdx >= 0) {
        columnStacks.value[parentIdx].selected = entry.path;
        columnStacks.value = columnStacks.value.slice(0, parentIdx + 1);
      }
      const list = await api.listDirectory(entry.path);
      currentPath.value = entry.path;
      entries.value = list;
      columnStacks.value.push({ path: entry.path, entries: list, selected: null });
    } else {
      await loadDir(entry.path);
    }
  }, "打开文件夹...");
}

async function onNavigate(path: string) {
  await withBusy(async () => {
    await loadDir(path);
  }, "跳转中...");
}

async function refreshCurrent() {
  if (!currentPath.value) return;
  await withBusy(async () => {
    const keep = [...selectedPaths.value];
    await loadDir(currentPath.value);
    if (keep.length) {
      const exist = new Set(entries.value.map((e) => e.path));
      for (const col of columnStacks.value) {
        for (const e of col.entries) exist.add(e.path);
      }
      const restored = keep.filter((p) => exist.has(p));
      if (restored.length) {
        const primary =
          (selectedEntry.value && restored.includes(selectedEntry.value.path)
            ? selectedEntry.value
            : resolveEntriesByPaths([restored[0]])[0]) || null;
        setSelection(restored, primary);
      }
    } else if (selectedEntry.value) {
      await loadPreviewFor(selectedEntry.value);
    }
  }, "刷新中...");
}

function placeMenu(x: number, y: number, size?: { width?: number; height?: number }) {
  const pad = 8;
  const menuWidth = size?.width || 260;
  const menuHeight = size?.height || 420;
  const vw = window.innerWidth;
  const vh = window.innerHeight;

  let nx = x;
  let ny = y;
  // 默认从点击点向右下展开；不够则翻到左侧/上方
  if (nx + menuWidth + pad > vw) nx = Math.max(pad, x - menuWidth);
  if (ny + menuHeight + pad > vh) ny = Math.max(pad, y - menuHeight);
  nx = Math.min(Math.max(pad, nx), Math.max(pad, vw - menuWidth - pad));
  ny = Math.min(Math.max(pad, ny), Math.max(pad, vh - menuHeight - pad));
  return { x: Math.round(nx), y: Math.round(ny) };
}

function openMenu(partial: Omit<ContextMenuState, "visible" | "x" | "y"> & { x: number; y: number }) {
  const pos = placeMenu(partial.x, partial.y);
  // 先用估算位置打开；ContextMenu 渲染后会按真实尺寸 reposition
  contextMenu.value = {
    visible: true,
    x: pos.x,
    y: pos.y,
    mode: partial.mode,
    entry: partial.entry,
    workspace: partial.workspace,
  };
}

function onContextMenuReposition(pos: { x: number; y: number }) {
  if (!contextMenu.value.visible) return;
  if (contextMenu.value.x === pos.x && contextMenu.value.y === pos.y) return;
  contextMenu.value = {
    ...contextMenu.value,
    x: pos.x,
    y: pos.y,
  };
}

function onFileContext(payload: { entry: FsEntry; x: number; y: number }) {
  openMenu({
    mode: "file",
    entry: payload.entry,
    workspace: null,
    x: payload.x,
    y: payload.y,
  });
}

function onWorkspaceContext(payload: { workspace: Workspace; x: number; y: number }) {
  openMenu({
    mode: "workspace",
    entry: null,
    workspace: payload.workspace,
    x: payload.x,
    y: payload.y,
  });
}

function closeContext() {
  contextMenu.value.visible = false;
  contextMenu.value.entry = null;
  contextMenu.value.workspace = null;
}

function showOutput(title: string, text: string) {
  modalTitle.value = title;
  modalOutput.value = text || "(无输出)";
  modalType.value = "output";
}

function closeModal() {
  modalType.value = null;
}

function closeDiffViewer() {
  diffViewerOpen.value = false;
  diffViewerRevision.value = null;
  diffViewerFiles.value = null;
  diffViewerFocusPath.value = null;
}

async function openDiffViewer(
  path: string,
  title?: string,
  revision?: string | null,
  options?: { files?: DiffFileInfo[] | null; focusPath?: string | null },
) {
  if (!path) {
    toast("没有可对比的路径", "info");
    return;
  }
  diffViewerPath.value = path;
  diffViewerTitle.value = title || `DIFF · ${path.split("/").pop() || path}`;
  diffViewerRevision.value = revision || null;
  diffViewerFiles.value = options?.files?.length ? [...options.files] : null;
  diffViewerFocusPath.value = options?.focusPath || options?.files?.[0]?.path || null;
  diffViewerOpen.value = true;
}

function buildHistoryDiffFiles(entry: SvnLogEntry): DiffFileInfo[] {
  const out: DiffFileInfo[] = [];
  const seen = new Set<string>();
  for (const item of entry.paths || []) {
    if ((item.kind || "").toLowerCase() === "dir") continue;
    if (isUnsupportedDiffPath(item.path, { kind: item.kind })) continue;
    const local = resolveHistoryLocalPath(item.path);
    if (!local || seen.has(local)) continue;
    if (isUnsupportedDiffPath(local)) continue;
    seen.add(local);
    const name = local.split("/").pop() || item.path.split("/").filter(Boolean).pop() || item.path;
    const meta = getSvnStatusMeta(item.action);
    out.push({
      path: local,
      relativePath: (item.path || "").replace(/^\//, ""),
      name,
      status: item.action || "M",
      statusLabel: meta?.label || item.action || "变更",
      binary: false,
      isDir: false,
    });
  }
  return out;
}

async function openHistoryRevisionDiff(entry: SvnLogEntry, focusItem?: SvnLogPath | null) {
  selectHistoryEntry(entry);
  const files = buildHistoryDiffFiles(entry);
  if (!files.length) {
    toast("该次提交没有可映射的本地文件，无法打开差异", "info");
    return;
  }
  let focus = files[0].path;
  if (focusItem) {
    const local = resolveHistoryLocalPath(focusItem.path);
    if (local && files.some((f) => f.path === local)) focus = local;
    historySelectedAction.value = focusItem.action || files.find((f) => f.path === focus)?.status || "M";
  } else {
    historySelectedAction.value = files[0].status || "M";
  }
  const root = historyWcLocal.value || historyRoot.value || activeWorkspace.value?.path || files[0].path;
  await openDiffViewer(root, `历史版本 r${entry.revision}`, entry.revision, {
    files,
    focusPath: focus,
  });
}

async function openHistoryDialog(targetPath?: string) {
  const path = (targetPath || activeWorkspace.value?.path || "").trim();
  if (!path) {
    toast("请先选择工作副本或文件", "info");
    return;
  }
  historyRoot.value = path;
  historyItems.value = [];
  historyLoading.value = true;
  historySelectedRevision.value = "";
  historySelectedAction.value = "";
  historyWcLocal.value = activeWorkspace.value?.path || path;
  historyRepoPrefix.value = "";
  modalType.value = "history";
  try {
    await prepareHistoryContext(path);
    historyItems.value = await api.svnLogEntries(path, 80);
    if (historyItems.value.length) {
      selectHistoryEntry(historyItems.value[0]);
    } else {
      toast("没有找到历史记录", "info");
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    toast(msg || "读取历史失败", "error");
    historyItems.value = [];
  } finally {
    historyLoading.value = false;
  }
}

function selectHistoryEntry(entry: SvnLogEntry) {
  historySelectedRevision.value = entry.revision;
  historySelectedAction.value =
    entry.paths.find((p) => {
      const leaf = historyRoot.value.split("/").pop() || "";
      return p.path === historyRoot.value || (leaf && p.path.endsWith(`/${leaf}`));
    })?.action ||
    entry.paths[0]?.action ||
    "M";
}

async function refreshHistoryDialog() {
  if (!historyRoot.value) return;
  historyLoading.value = true;
  try {
    historyItems.value = await api.svnLogEntries(historyRoot.value, 80);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    toast(msg || "刷新历史失败", "error");
  } finally {
    historyLoading.value = false;
  }
}

async function prepareHistoryContext(path: string) {
  historyRepoPrefix.value = "";
  historyWcLocal.value = activeWorkspace.value?.path || path;
  try {
    // 先对目标路径取 info，拿到 Working Copy Root，再对 WC 根取 URL 前缀
    const probe = await api.svnInfo(path);
    const probeOut = probe?.stdout || "";
    const wcRoot =
      probeOut.match(/^Working Copy Root Path:\s*(.+)$/m)?.[1]?.trim() ||
      activeWorkspace.value?.path ||
      path;
    historyWcLocal.value = wcRoot;

    const res = await api.svnInfo(wcRoot);
    const stdout = res?.stdout || "";
    const url = stdout.match(/^URL:\s*(.+)$/m)?.[1]?.trim();
    const root = stdout.match(/^Repository Root:\s*(.+)$/m)?.[1]?.trim();
    if (url && root && url.startsWith(root)) {
      // 仓库根检出时 prefix 为空字符串；子目录检出时为 /trunk/xxx
      let prefix = url.slice(root.length);
      if (prefix && !prefix.startsWith("/")) prefix = `/${prefix}`;
      historyRepoPrefix.value = prefix.replace(/\/$/, "");
    } else {
      historyRepoPrefix.value = "";
    }
  } catch {
    historyRepoPrefix.value = "";
  }
}

function resolveHistoryLocalPath(repoPath: string): string | null {
  const rp = (repoPath || "").trim();
  if (!rp) return null;
  const normalized = (rp.startsWith("/") ? rp : `/${rp}`).replace(/\\/g, "/");
  const pref = (historyRepoPrefix.value || "").replace(/\/$/, "");
  const wc = (historyWcLocal.value || activeWorkspace.value?.path || "").replace(/\/$/, "");
  if (wc) {
    // pref 为空：工作副本就是仓库根，仓库路径整段拼到本地
    if (!pref) {
      const rel = normalized.replace(/^\//, "");
      return rel ? `${wc}/${rel}` : wc;
    }
    if (normalized === pref || normalized.startsWith(`${pref}/`)) {
      const rel = normalized.slice(pref.length).replace(/^\//, "");
      return rel ? `${wc}/${rel}` : wc;
    }
  }
  // 单文件历史：直接使用当前 historyRoot
  const root = historyRoot.value;
  if (root) {
    const leaf = root.split("/").pop() || "";
    if (leaf && (normalized.endsWith(`/${leaf}`) || normalized === `/${leaf}`)) {
      return root;
    }
  }
  return null;
}

async function onHistoryViewPath(payload: { entry: SvnLogEntry; path: SvnLogPath }) {
  const entry = payload.entry;
  const item = payload.path;
  if ((item.kind || "").toLowerCase() === "dir") {
    toast("目录不支持查看文本差异，可继续浏览提交详情", "info");
    return;
  }
  const local = resolveHistoryLocalPath(item.path);
  if (!local) {
    toast(`无法映射本地路径：${item.path}`, "info");
    return;
  }
  await openHistoryRevisionDiff(entry, item);
}

async function onHistoryViewRevision(entry: SvnLogEntry) {
  await openHistoryRevisionDiff(entry, null);
}

async function actionTargets(entry: FsEntry | null): Promise<string[]> {
  if (!entry) return [];
  if (selectedPaths.value.includes(entry.path) && selectedPaths.value.length > 1) {
    return [...selectedPaths.value];
  }
  return [entry.path];
}

function summarizePaths(paths: string[]) {
  if (paths.length <= 1) return paths[0] || "";
  return `${paths[0]} 等 ${paths.length} 项`;
}

function filterRevertablePaths(paths: string[]): string[] {
  const entries = resolveEntriesByPaths(paths);
  const byPath = new Map(entries.map((e) => [e.path, e]));
  // 未纳入版本控制 / 忽略 / 外部引用 不可还原
  return paths.filter((p) => {
    const entry = byPath.get(p);
    // 变更弹窗等场景可能不在当前目录列表里，若无本地状态信息则允许尝试
    if (!entry) return true;
    // 无 svn 状态通常表示正常版本文件，对整目录/正常文件还原也合理
    if (!entry.svnStatus) return true;
    return canRevertSvnStatus(entry.svnStatus);
  });
}

async function confirmRevert(paths: string[], label?: string): Promise<boolean> {
  if (!paths.length) return false;
  const multi = paths.length > 1;
  const title = label || (multi ? `选中的 ${paths.length} 项` : paths[0]);
  const detail = multi ? summarizePaths(paths) : paths[0];
  const message =
    `确认还原「${title}」到版本库状态？\n\n` +
    `${detail}\n\n` +
    "本地未提交修改将丢失，此操作不可撤销。";

  // Tauri WebView 中 window.confirm 常常不弹/无效，统一用原生确认框
  try {
    return await nativeConfirm(message, {
      title: "确认还原",
      kind: "warning",
      okLabel: "还原",
      cancelLabel: "取消",
    });
  } catch (e) {
    // 兜底：极少数环境原生对话框不可用时再试 window.confirm
    console.warn("native confirm failed, fallback to window.confirm", e);
    return window.confirm(message);
  }
}


function primaryTargetPath() {
  if (selectedEntry.value?.path) return selectedEntry.value.path;
  if (selectedPaths.value.length) return selectedPaths.value[selectedPaths.value.length - 1];
  return currentPath.value || activeWorkspace.value?.path || "";
}

/** 工具栏/快捷键提交时使用：优先整组多选，否则当前主目标 */
function commitTargetPaths(): string[] {
  if (selectedPaths.value.length > 1) {
    return [...selectedPaths.value];
  }
  if (selectedPaths.value.length === 1) {
    return [selectedPaths.value[0]];
  }
  if (selectedEntry.value?.path) {
    return [selectedEntry.value.path];
  }
  const fallback = currentPath.value || activeWorkspace.value?.path || "";
  return fallback ? [fallback] : [];
}

function parentDirOf(path: string) {
  const idx = Math.max(path.lastIndexOf("/"), path.lastIndexOf("\\"));
  return idx > 0 ? path.slice(0, idx) : path;
}

/** 为多个选中路径计算共同的 svn 提交 cwd */
function computeCommitRoot(targets: string[]): string {
  const workspace = activeWorkspace.value?.path || "";
  if (targets.length === 1) {
    const only = targets[0];
    const entry =
      resolveEntriesByPaths([only])[0] ||
      (selectedEntry.value?.path === only ? selectedEntry.value : null);
    if (entry?.isDir) return only;
    if (entry && !entry.isDir) return parentDirOf(only);
    // 未知类型时优先当前目录/工作副本，避免把文件路径当 cwd
    return currentPath.value || workspace || parentDirOf(only) || only;
  }

  // 多选：取所有目标的最长公共父目录；再回落到工作副本根
  const normalized = targets.map((p) => p.replace(/\\/g, "/"));
  let prefix = normalized[0] || "";
  for (let i = 1; i < normalized.length; i++) {
    const cur = normalized[i];
    let j = 0;
    const max = Math.min(prefix.length, cur.length);
    while (j < max && prefix[j] === cur[j]) j++;
    prefix = prefix.slice(0, j);
    if (!prefix) break;
  }
  // 回退到最后一个完整目录段，避免截断在文件名中间
  if (prefix && !prefix.endsWith("/")) {
    const cut = prefix.lastIndexOf("/");
    prefix = cut > 0 ? prefix.slice(0, cut) : prefix;
  }
  prefix = prefix.replace(/\/+$/, "");
  if (prefix) return prefix;
  return currentPath.value || workspace || targets[0];
}


async function runUpdateOn(path: string, title = "更新进度") {
  if (!path) {
    toast("请先选择工作副本或文件", "info");
    return;
  }
  if (progress.value.running) {
    toast("已有任务进行中，请稍候", "info");
    return;
  }
  const jobId = newJobId("update");
  openProgress(title, jobId);
  appendProgressLine("已创建更新任务，正在启动...");
  statusText.value = "更新中...";
  await nextTick();
  try {
    await api.svnUpdate(path, jobId);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    appendProgressLine(`[stderr] ${msg}`);
    finishProgress(false, msg);
    toast(msg, "error");
    statusText.value = `错误: ${msg}`;
  }
}

async function openChangesDialog(targetPath?: string) {
  const path = targetPath || activeWorkspace.value?.path || currentPath.value;
  if (!path) {
    toast("请先选择工作副本", "info");
    return;
  }
  changesRoot.value = path;
  changesItems.value = [];
  changesLoading.value = true;
  modalType.value = "changes";
  try {
    const items = await api.svnStatus(path, true);
    changesItems.value = items.filter((i) => i.status && i.status !== "X" && i.status !== "I");
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    toast(msg || "读取变更失败", "error");
    changesItems.value = [];
  } finally {
    changesLoading.value = false;
  }
}

async function refreshChangesDialog() {
  if (!changesRoot.value) return;
  changesLoading.value = true;
  try {
    const items = await api.svnStatus(changesRoot.value, true);
    changesItems.value = items.filter((i) => i.status && i.status !== "X" && i.status !== "I");
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    toast(msg || "刷新变更失败", "error");
  } finally {
    changesLoading.value = false;
  }
}

async function onToolbarUpdate() {
  const path = primaryTargetPath();
  await runUpdateOn(path);
}

async function onToolbarCommit() {
  const paths = commitTargetPaths();
  if (!paths.length) {
    toast("请先选择要提交的文件或文件夹", "info");
    return;
  }
  // 多选文件夹 + 文件：遍历每个文件夹内部变更，并合并选中文件的变更
  await openCommitDialog(paths);
}

async function runAction(action: ContextAction) {
  const entry = contextMenu.value.entry;
  closeContext();
  if (!entry) return;
  const paths = await actionTargets(entry);
  const path = paths[0];
  const multi = paths.length > 1;

  if (action === "reveal") {
    await withBusy(async () => {
      await api.revealInFinder(path);
    }, "打开 Finder...");
    return;
  }

  if (action === "commit") {
    // 文件/文件夹/多选：收集各自范围内的变更，供提交弹窗勾选
    await openCommitDialog(paths);
    return;
  }

  if (action === "add") {
    const res = await withBusy(async () => api.svnAdd(paths), multi ? `添加 ${paths.length} 项...` : "添加到版本控制...");
    if (res) {
      showOutput("添加结果", [res.stdout, res.stderr].filter(Boolean).join("\n") || "add 完成");
      await refreshCurrent();
      toast(res.success ? "已添加到版本控制" : "添加结束（有警告）", res.success ? "success" : "info");
    }
    return;
  }

  if (action === "ignore") {
    if (multi) {
      toast("忽略仅支持单选", "info");
      return;
    }
    const res = await withBusy(async () => api.svnIgnore(path), "添加到忽略...");
    if (res) {
      showOutput("忽略结果", [res.stdout, res.stderr].filter(Boolean).join("\n") || "ignore 完成");
      await refreshCurrent();
      toast(res.success ? "已加入忽略列表" : "忽略结束（有警告）", res.success ? "success" : "info");
    }
    return;
  }

  if (action === "resolved") {
    if (multi) {
      toast("标记已解决仅支持单选", "info");
      return;
    }
    const res = await withBusy(async () => api.svnResolved(path), "标记已解决...");
    if (res) {
      showOutput("已解决", [res.stdout, res.stderr].filter(Boolean).join("\n") || "resolved 完成");
      await refreshCurrent();
      toast(res.success ? "已标记为解决" : "操作结束（有警告）", res.success ? "success" : "info");
    }
    return;
  }

  if (action === "info") {
    if (multi) {
      toast("信息查看仅支持单选", "info");
      return;
    }
    const res = await withBusy(async () => api.svnInfo(path), "获取信息...");
    if (res) showOutput(`信息 · ${entry.name}`, [res.stdout, res.stderr].filter(Boolean).join("\n") || "(无信息)");
    return;
  }

  if (action === "proplist") {
    if (multi) {
      toast("属性查看仅支持单选", "info");
      return;
    }
    const res = await withBusy(async () => api.svnProplist(path), "获取属性...");
    if (res) showOutput(`属性 · ${entry.name}`, [res.stdout, res.stderr].filter(Boolean).join("\n") || "(无属性)");
    return;
  }

  if (action === "blame") {
    if (multi || entry.isDir) {
      toast("注解(Blame)仅支持单个文件", "info");
      return;
    }
    const res = await withBusy(async () => api.svnBlame(path), "获取注解...");
    if (res) showOutput(`注解 · ${entry.name}`, [res.stdout, res.stderr].filter(Boolean).join("\n") || "(无注解)");
    return;
  }

  if (action === "lock") {
    const res = await withBusy(async () => api.svnLock(paths), multi ? `锁定 ${paths.length} 项...` : "锁定中...");
    if (res) {
      showOutput("锁定结果", [res.stdout, res.stderr].filter(Boolean).join("\n") || "lock 完成");
      await refreshCurrent();
      toast(res.success ? "锁定完成" : "锁定结束（有警告）", res.success ? "success" : "info");
    }
    return;
  }

  if (action === "unlock") {
    const res = await withBusy(async () => api.svnUnlock(paths), multi ? `解锁 ${paths.length} 项...` : "解锁中...");
    if (res) {
      showOutput("解锁结果", [res.stdout, res.stderr].filter(Boolean).join("\n") || "unlock 完成");
      await refreshCurrent();
      toast(res.success ? "解锁完成" : "解锁结束（有警告）", res.success ? "success" : "info");
    }
    return;
  }

  if (action === "patch") {
    if (multi) {
      toast("导出补丁仅支持单选", "info");
      return;
    }
    const res = await withBusy(async () => api.svnPatch(path), "导出补丁...");
    if (res) showOutput(`补丁 · ${entry.name}`, [res.stdout, res.stderr].filter(Boolean).join("\n") || "(无差异)");
    return;
  }

  if (action === "rename") {
    if (multi) {
      toast("重命名仅支持单选", "info");
      return;
    }
    renameKind.value = "file";
    renameTarget.value = path;
    renameWorkspaceId.value = "";
    renameFromName.value = entry.name;
    modalType.value = "rename";
    return;
  }

  if (action === "localDelete" || action === "svnDelete") {
    const isLocal = action === "localDelete";
    const ok = window.confirm(
      multi
        ? `确认${isLocal ? "本地删除" : "SVN 删除"}选中的 ${paths.length} 项？\n${summarizePaths(paths)}\n\n${
            isLocal
              ? "将直接从磁盘删除本地文件/文件夹（不会执行 svn delete）。"
              : "将执行 svn delete，标记为版本库删除（需提交后才会从仓库移除）。"
          }`
        : `确认${isLocal ? "本地删除" : "SVN 删除"}？\n${path}\n\n${
            isLocal
              ? "将直接从磁盘删除本地文件/文件夹（不会执行 svn delete）。"
              : "将执行 svn delete，标记为版本库删除（需提交后才会从仓库移除）。"
          }`,
    );
    if (!ok) return;
    const res = await withBusy(async () => {
      const outputs: string[] = [];
      let allOk = true;
      for (const p of paths) {
        const r = isLocal ? await api.localDelete(p) : await api.svnDelete(p, true);
        allOk = allOk && r.success;
        const chunk = [r.stdout, r.stderr].filter(Boolean).join("\n");
        if (chunk) outputs.push(`# ${p}\n${chunk}`);
        if (!r.success && !chunk) outputs.push(`# ${p}\n删除失败`);
      }
      return { success: allOk, stdout: outputs.join("\n\n"), stderr: "", code: allOk ? 0 : 1 };
    }, multi ? `${isLocal ? "本地删除" : "SVN 删除"} ${paths.length} 项...` : `${isLocal ? "本地删除" : "SVN 删除"}中...`);
    if (res) {
      if (!res.success) {
        showOutput(isLocal ? "本地删除结果" : "SVN 删除结果", res.stdout || "删除失败");
      }
      toast(
        multi
          ? `已处理${isLocal ? "本地删除" : "SVN 删除"} ${paths.length} 项`
          : isLocal
            ? "已本地删除"
            : "已标记 SVN 删除",
        res.success ? "success" : "error",
      );
      selectedEntry.value = null;
      selectedPaths.value = [];
      selectionAnchorPath.value = null;
      preview.value = null;
      await refreshCurrent();
    }
    return;
  }

  if (action === "clean") {
    if (multi) {
      toast("Clean 仅支持单选", "info");
      return;
    }
    const res = await withBusy(async () => api.svnClean(path), "Clean 中...");
    if (res) {
      showOutput("Clean 结果", [res.stdout, res.stderr].filter(Boolean).join("\n") || "cleanup 完成");
      await refreshCurrent();
      toast(res.success ? "Clean 完成" : "Clean 结束（有警告）", res.success ? "success" : "info");
    }
    return;
  }

  if (action === "update") {
    if (multi) {
      toast("更新仅支持单选目标（可对文件夹更新）", "info");
      return;
    }
    await runUpdateOn(path, `更新进度 · ${entry.name}`);
    return;
  }

  if (action === "diff") {
    if (multi) {
      toast("DIFF 仅支持单选", "info");
      return;
    }
    await openDiffViewer(path, `DIFF · ${entry.name}`);
    return;
  }

  if (action === "log") {
    if (multi) {
      toast("查看历史仅支持单选", "info");
      return;
    }
    await openHistoryDialog(path);
    return;
  }

  if (action === "revert") {
    const revertable = filterRevertablePaths(paths);
    const skipped = paths.length - revertable.length;
    if (!revertable.length) {
      toast("选中项均未纳入版本控制，无法还原", "info");
      return;
    }
    if (skipped > 0) {
      toast(`已跳过 ${skipped} 个未纳入版本控制的项`, "info");
    }
    if (!(await confirmRevert(revertable, multi ? `选中的 ${revertable.length} 项` : entry.name))) return;
    const res = await withBusy(async () => {
      const outputs: string[] = [];
      let allOk = true;
      for (const p of revertable) {
        const r = await api.svnRevert(p);
        allOk = allOk && r.success;
        const chunk = [r.stdout, r.stderr].filter(Boolean).join("\n");
        if (chunk) outputs.push("# " + p + "\n" + chunk);
      }
      return { success: allOk, stdout: outputs.join("\n\n"), stderr: "", code: allOk ? 0 : 1 };
    }, multi ? `还原 ${revertable.length} 项...` : "还原中...");
    if (res) {
      showOutput(
        multi ? `还原结果 · ${revertable.length} 项` : "还原结果",
        [res.stdout, res.stderr].filter(Boolean).join("\n") || "revert 完成",
      );
      await refreshCurrent();
      toast(res.success ? "还原完成" : "还原结束（有警告）", res.success ? "success" : "info");
    }
    return;
  }
}

async function onRename(newName: string) {
  if (renameKind.value === "workspace") {
    const id = renameWorkspaceId.value;
    if (!id) return;
    const res = await withBusy(async () => api.renameWorkspace(id, newName), "重命名工作副本...");
    if (res) {
      modalType.value = null;
      await refreshWorkspaces(id);
      toast("工作副本已重命名", "success");
    }
    return;
  }

  const path = renameTarget.value;
  if (!path) return;
  const res = await withBusy(async () => api.svnRename(path, newName), "重命名中...");
  if (res) {
    modalType.value = null;
    toast("重命名完成", "success");
    selectedEntry.value = null;
    selectedPaths.value = [];
    selectionAnchorPath.value = null;
    preview.value = null;
    await refreshCurrent();
  }
}

async function runWorkspaceAction(action: WorkspaceAction) {
  const ws = contextMenu.value.workspace;
  closeContext();
  if (!ws) return;
  const path = ws.path;

  // 先选中该工作副本
  if (activeId.value !== ws.id) {
    await selectWorkspace(ws.id);
  }

  if (action === "reveal") {
    await withBusy(async () => {
      await api.revealInFinder(path);
    }, "打开 Finder...");
    return;
  }

  if (action === "commit") {
    await openCommitDialog(path);
    return;
  }

  if (action === "info") {
    const res = await withBusy(async () => api.svnInfo(path), "获取信息...");
    if (res) showOutput(`信息 · ${ws.name}`, [res.stdout, res.stderr].filter(Boolean).join("\n") || "(无信息)");
    return;
  }

  if (action === "switch") {
    switchTarget.value = path;
    modalType.value = "switch";
    return;
  }

  if (action === "patch") {
    const res = await withBusy(async () => api.svnPatch(path), "导出补丁...");
    if (res) showOutput(`补丁 · ${ws.name}`, [res.stdout, res.stderr].filter(Boolean).join("\n") || "(无差异)");
    return;
  }

  if (action === "rename") {
    renameKind.value = "workspace";
    renameWorkspaceId.value = ws.id;
    renameTarget.value = "";
    renameFromName.value = ws.name;
    modalType.value = "rename";
    return;
  }

  if (action === "remove") {
    await onRemoveWorkspace(ws.id);
    return;
  }

  if (action === "clean") {
    const res = await withBusy(async () => api.svnClean(path), "Clean 中...");
    if (res) {
      showOutput("Clean 结果", [res.stdout, res.stderr].filter(Boolean).join("\n") || "cleanup 完成");
      await refreshCurrent();
      toast(res.success ? "Clean 完成" : "Clean 结束（有警告）", res.success ? "success" : "info");
    }
    return;
  }

  if (action === "update") {
    await runUpdateOn(path, `更新进度 · ${ws.name}`);
    return;
  }

  if (action === "diff") {
    await openDiffViewer(path, `DIFF · ${ws.name}`);
    return;
  }

  if (action === "log") {
    await openHistoryDialog(path);
    return;
  }

  if (action === "revert") {
    if (!(await confirmRevert([path], `工作副本「${ws.name}」`))) return;
    const res = await withBusy(async () => api.svnRevert(path), "还原中...");
    if (res) {
      showOutput("还原结果", [res.stdout, res.stderr].filter(Boolean).join("\n") || "revert 完成");
      await refreshCurrent();
      toast(res.success ? "还原完成" : "还原结束（有警告）", res.success ? "success" : "info");
    }
    return;
  }
}

async function openCommitDialog(target: string | string[]) {
  // 规范化目标：数组 = 多选文件/文件夹；字符串 = 单个目标
  const targets = Array.from(
    new Set(
      (Array.isArray(target) ? target : [target])
        .map((p) => (p || "").trim())
        .filter(Boolean),
    ),
  );
  if (!targets.length) {
    toast("请先选择要提交的文件或文件夹", "info");
    return;
  }

  // 提交 cwd：
  // - 单文件：父目录
  // - 单文件夹：该文件夹
  // - 多选：公共父目录 / 工作副本根
  const root = computeCommitRoot(targets);
  commitTarget.value = root;
  commitItems.value = [];
  commitLoading.value = true;
  modalType.value = "commit";
  try {
    // 始终走 many：对每个选中目标分别取 status 后合并
    // 文件夹会递归遍历内部变更，文件只取自身；最终进入待勾选提交列表
    const items = await api.svnStatusMany(targets, true);
    // 排除外部引用与忽略项；保留 ?/M/A/D/C/R/!/~ 等可提交项
    // 目录节点若本身有状态也保留（例如未版本目录）
    commitItems.value = items.filter((i) => i.status && i.status !== "X" && i.status !== "I");
    if (!commitItems.value.length) {
      toast("选中范围内没有可提交的变更", "info");
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    toast(msg || "读取变更失败", "error");
    commitItems.value = [];
  } finally {
    commitLoading.value = false;
  }
}

async function onCommit(payload: { message: string; paths: string[] }) {
  const path = commitTarget.value;
  if (!path) return;
  if (!payload.paths.length) {
    toast("请至少勾选一个变更文件", "info");
    return;
  }
  const res = await withBusy(
    async () => api.svnCommit(path, payload.message, payload.paths),
    `提交 ${payload.paths.length} 项...`,
  );
  if (res) {
    modalType.value = null;
    commitItems.value = [];
    showOutput("提交结果", [res.stdout, res.stderr].filter(Boolean).join("\n"));
    await refreshCurrent();
    toast(res.success ? "提交成功" : "提交结束", res.success ? "success" : "info");
  }
}

async function onSwitch(payload: { url: string }) {
  const path = switchTarget.value || activeWorkspace.value?.path;
  if (!path) return;
  const res = await withBusy(async () => api.svnSwitch(path, payload.url), "切换中...");
  if (res) {
    modalType.value = null;
    showOutput("Switch 结果", [res.stdout, res.stderr].filter(Boolean).join("\n") || "switch 完成");
    await refreshCurrent();
    toast(res.success ? "切换完成" : "切换结束（有警告）", res.success ? "success" : "info");
  }
}

async function onChangesAction(payload: { action: "diff" | "revert" | "commit" | "reveal"; path: string }) {
  if (payload.action === "commit") {
    modalType.value = null;
    await openCommitDialog(payload.path || changesRoot.value || activeWorkspace.value?.path || "");
    return;
  }
  if (!payload.path) return;
  if (payload.action === "diff") {
    await openDiffViewer(payload.path, `DIFF · ${payload.path.split("/").pop() || payload.path}`);
    return;
  }
  if (payload.action === "reveal") {
    await withBusy(async () => api.revealInFinder(payload.path), "打开 Finder...");
    return;
  }
  if (payload.action === "revert") {
    // 未版本控制项在 UI 层已隐藏；这里再兜底一次
    const hit = (changesItems.value || []).find((i) => i.path === payload.path);
    if (hit && !canRevertSvnStatus(hit.status)) {
      toast("未纳入版本控制的项无法还原", "info");
      return;
    }
    if (!(await confirmRevert([payload.path]))) return;
    const res = await withBusy(async () => api.svnRevert(payload.path), "还原中...");
    if (res) {
      toast(res.success ? "已还原" : "还原结束（有警告）", res.success ? "success" : "info");
      await refreshChangesDialog();
      await refreshCurrent();
    }
  }
}

async function onChangeView(mode: ViewMode) {
  viewMode.value = mode;
  if (!currentPath.value) return;
  if (mode === "columns") {
    await withBusy(async () => {
      await rebuildColumns(currentPath.value, selectedEntry.value?.path || null);
    }, "切换分栏视图...");
  }
}

function isTypingTarget(target: EventTarget | null) {
  const el = target as HTMLElement | null;
  if (!el) return false;
  const tag = (el.tagName || "").toLowerCase();
  return tag === "input" || tag === "textarea" || tag === "select" || el.isContentEditable;
}

function onGlobalKeydown(e: KeyboardEvent) {
  if (isTypingTarget(e.target)) return;
  if (e.key === "Escape") {
    if (contextMenu.value.visible) {
      closeContext();
      return;
    }
    if (modalType.value && !busy.value && !progress.value.running) {
      modalType.value = null;
      return;
    }
  }
  if (modalType.value) return;
  const mod = e.metaKey || e.ctrlKey;
  if (!mod) return;

  // ⌘R 刷新
  if (e.key.toLowerCase() === "r") {
    e.preventDefault();
    void refreshCurrent();
    return;
  }
  // ⌘U 更新
  if (e.key.toLowerCase() === "u") {
    e.preventDefault();
    void onToolbarUpdate();
    return;
  }
  // ⌘Enter 提交
  if (e.key === "Enter") {
    e.preventDefault();
    void onToolbarCommit();
    return;
  }
  // ⌘⇧C 本地变更
  if (e.key.toLowerCase() === "c" && e.shiftKey) {
    e.preventDefault();
    void openChangesDialog();
    return;
  }
  // ⌘⇧H 提交历史
  if (e.key.toLowerCase() === "h" && e.shiftKey) {
    e.preventDefault();
    void openHistoryDialog();
    return;
  }
}

async function maximizeAppWindow() {
  try {
    const win = getCurrentWindow();
    // 优先最大化到当前屏幕可用区域
    const maximized = await win.isMaximized();
    if (!maximized) {
      await win.maximize();
    }
    await win.setFocus();
  } catch {
    // 非 Tauri 环境（纯浏览器预览）忽略
  }
}

onMounted(async () => {
  window.addEventListener("keydown", onGlobalKeydown);
  void maximizeAppWindow();
  try {
    progressUnlisten = await listen<SvnProgressEvent>("svn-progress", (event) => {
      handleProgressEvent(event.payload);
    });
    await refreshWorkspaces();
    if (activeId.value) {
      const ws = workspaces.value.find((w) => w.id === activeId.value);
      if (ws) {
        await loadDir(ws.path);
      }
    }
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    toast(msg, "error");
  }
});

onUnmounted(() => {
  document.body.classList.remove("is-resizing-layout");
  window.removeEventListener("keydown", onGlobalKeydown);
  if (progressUnlisten) {
    progressUnlisten();
    progressUnlisten = null;
  }
});
</script>

<template>
  <div class="app-shell" :class="{ 'preview-collapsed': previewCollapsed }" :style="shellStyle">
    <Sidebar
      :workspaces="workspaces"
      :active-id="activeId"
      :busy="busy"
      @select="selectWorkspace"
      @add="onAddWorkspace"
      @checkout="openCheckoutModal"
      @context="onWorkspaceContext"
    />

    <div
      class="layout-resizer layout-resizer-sidebar"
      title="拖拽调整工作副本宽度"
      @mousedown="onSidebarResizeStart"
    />

    <FileExplorer
      :entries="entries"
      :selected-paths="selectedPaths"
      :view-mode="viewMode"
      :breadcrumb="breadcrumb"
      :column-stacks="columnStacks"
      :busy="busy"
      :workspace-path="activeWorkspace?.path || null"
      @select="onSelectEntry"
      @select-paths="onSelectPaths"
      @open="onOpenEntry"
      @navigate="onNavigate"
      @context="onFileContext"
      @change-view="onChangeView"
      @refresh="refreshCurrent"
      @update="onToolbarUpdate"
      @commit="onToolbarCommit"
      @changes="openChangesDialog()"
      @history="openHistoryDialog()"
      @copied="toast('已复制路径', 'success')"
      @copy-failed="(msg) => toast(msg || '复制失败', 'error')"
    />

    <div
      class="layout-resizer layout-resizer-preview"
      :class="{ disabled: previewCollapsed }"
      :title="previewCollapsed ? '预览区已收起' : '拖拽调整预览区宽度'"
      @mousedown="onPreviewResizeStart"
    />

    <PreviewPanel
      :preview="preview"
      :busy="previewBusy"
      :collapsed="previewCollapsed"
      @toggle-collapse="togglePreviewCollapsed"
    />

    <div class="status-bar">
      <div>{{ statusText }}</div>
      <div class="tiny">
        <span v-if="activeWorkspace">
          {{ activeWorkspace.name }} · {{ currentPath || activeWorkspace.path }}
          <template v-if="selectedPaths.length"> · 已选 {{ selectedPaths.length }} 项</template>
        </span>
        <span v-else>未选择工作副本</span>
      </div>
    </div>

    <ContextMenu
      :visible="contextMenu.visible"
      :x="contextMenu.x"
      :y="contextMenu.y"
      :mode="contextMenu.mode"
      :entry="contextMenu.entry"
      :workspace="contextMenu.workspace"
      :selected-count="contextMenu.entry && selectedPaths.includes(contextMenu.entry.path) ? selectedPaths.length : 1"
      @close="closeContext"
      @reposition="onContextMenuReposition"
      @file-action="runAction"
      @workspace-action="runWorkspaceAction"
    />

    <Modals
      :type="modalType"
      :title="modalTitle"
      :output="modalOutput"
      :busy="busy"
      :default-path="activeWorkspace?.path"
      :rename-from="renameFromName"
      :progress="progress"
      :commit-root="commitTarget"
      :commit-items="commitItems"
      :commit-loading="commitLoading"
      :switch-root="switchTarget"
      :changes-root="changesRoot"
      :changes-items="changesItems"
      :changes-loading="changesLoading"
      :history-root="historyRoot"
      :history-items="historyItems"
      :history-loading="historyLoading"
      :history-selected-revision="historySelectedRevision"
      @close="closeModal"
      @close-progress="closeProgress"
      @checkout="onCheckout"
      @commit="onCommit"
      @rename="onRename"
      @switch="onSwitch"
      @changes-action="onChangesAction"
      @refresh-changes="refreshChangesDialog"
      @history-select="selectHistoryEntry"
      @history-view-path="onHistoryViewPath"
      @history-view-revision="onHistoryViewRevision"
      @refresh-history="refreshHistoryDialog"
    />

    <div v-if="diffViewerOpen" class="diff-overlay">
      <DiffViewer
        :root-path="diffViewerPath"
        :title="diffViewerTitle"
        :revision="diffViewerRevision"
        :revision-action="historySelectedAction"
        :revision-files="diffViewerFiles"
        :initial-path="diffViewerFocusPath"
        @close="closeDiffViewer"
      />
    </div>

    <div class="toasts">
      <div v-for="t in toasts" :key="t.id" class="toast" :class="t.type">{{ t.text }}</div>
    </div>
  </div>
</template>
