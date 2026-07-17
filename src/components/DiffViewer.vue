<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from "vue";
import * as api from "../api/svn";
import type { DiffFileContent, DiffFileInfo, DiffViewMode } from "../types";
import {
  assignDiffBlockIds,
  blockEdgeClass,
  blockTypeClass,
  buildLineDiff,
  collapseRows,
  escapeHtml,
  resolveHighlightLang,
  splitName,
  statusClass,
  statusIcon,
  statusLabel,
  type BuiltDiff,
  type UnifiedRow,
} from "../utils/diffEngine";
import { highlightCode } from "../utils/codeHighlight";
import { filterDiffableFiles, isUnsupportedDiffPath } from "../utils/diffSupport";

const props = defineProps<{
  rootPath: string;
  title?: string;
  revision?: string | null;
  revisionAction?: string | null;
  /** 历史提交时由外部传入的完整变更文件列表 */
  revisionFiles?: DiffFileInfo[] | null;
  /** 打开时优先选中的文件本地路径 */
  initialPath?: string | null;
}>();

const emit = defineEmits<{ close: [] }>();

const FONT_SIZE_MIN = 10;
const FONT_SIZE_MAX = 20;
const DEFAULT_FONT_FAMILY = ".AppleSystemUIFont";
const DEFAULT_FONT_SIZE = 14;
const SIDEBAR_MIN = 200;
const SIDEBAR_MAX = 640;

const FONT_STACKS: Record<string, string> = {
  ".AppleSystemUIFont": ".AppleSystemUIFont, -apple-system, BlinkMacSystemFont, system-ui, sans-serif",
  "system-ui": "system-ui, -apple-system, BlinkMacSystemFont, sans-serif",
  "-apple-system": "-apple-system, BlinkMacSystemFont, system-ui, sans-serif",
  "SF Mono": '"SF Mono", Menlo, Monaco, monospace',
  Menlo: "Menlo, Monaco, monospace",
  Monaco: "Monaco, Menlo, monospace",
  "JetBrains Mono": '"JetBrains Mono", Menlo, monospace',
  "Fira Code": '"Fira Code", Menlo, monospace',
  "Source Code Pro": '"Source Code Pro", Menlo, monospace',
  "Cascadia Code": '"Cascadia Code", Menlo, monospace',
  "Courier New": '"Courier New", Courier, monospace',
  "PingFang SC": '"PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif',
  "Hiragino Sans GB": '"Hiragino Sans GB", "PingFang SC", "Microsoft YaHei", sans-serif',
  "Microsoft YaHei": '"Microsoft YaHei", "PingFang SC", sans-serif',
  monospace: "monospace",
};

function clampFontSize(value: string | number) {
  const n = Number.parseInt(String(value), 10);
  if (!Number.isFinite(n)) return DEFAULT_FONT_SIZE;
  return Math.min(FONT_SIZE_MAX, Math.max(FONT_SIZE_MIN, n));
}

function clampSidebarWidth(value: string | number) {
  const n = Number.parseInt(String(value), 10);
  if (!Number.isFinite(n)) return 300;
  return Math.min(SIDEBAR_MAX, Math.max(SIDEBAR_MIN, n));
}

function readPref(key: string, fallback: string) {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}

function writePref(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // ignore
  }
}

const loading = ref(true);
const loadingFile = ref(false);
/** 取消过期的列表加载 / 后台统计 */
let loadToken = 0;
let statsToken = 0;
/** 已加载过的文件内容缓存，避免来回点击重复 cat */
const contentCache = new Map<string, DiffFileContent>();

function contentCacheKey(path: string) {
  return `${props.revision || "wc"}::${path}`;
}
const error = ref("");
const files = ref<Array<DiffFileInfo & { additions: number; deletions: number }>>([]);
const selectedPath = ref<string | null>(null);
const fileContent = ref<DiffFileContent | null>(null);
const builtDiff = ref<BuiltDiff | null>(null);
const fileFilter = ref("");
const mode = ref<DiffViewMode>((readPref("sf.diff.mode", "split") as DiffViewMode) || "split");
const syncScroll = ref(readPref("sf.diff.syncScroll", "1") !== "0");
const collapseUnchanged = ref(readPref("sf.diff.collapseUnchanged", "1") !== "0");
const showLineNo = ref(readPref("sf.diff.showLineNo", "1") !== "0");
const showPath = ref(readPref("sf.diff.showPath", "1") !== "0");
const fontFamily = ref(readPref("sf.diff.fontFamily", DEFAULT_FONT_FAMILY));
const fontSize = ref(clampFontSize(readPref("sf.diff.fontSize", String(DEFAULT_FONT_SIZE))));
const sidebarWidth = ref(clampSidebarWidth(readPref("sf.diff.sidebarWidth", "300")));
const expandedHunks = ref<Set<string>>(new Set());
const currentDiffIndex = ref(-1);
const diffAnchors = ref<Array<{ id: number; el: HTMLElement }>>([]);
const syncingScroll = ref(false);
const diffRoot = ref<HTMLElement | null>(null);
const leftScroll = ref<HTMLElement | null>(null);
const rightScroll = ref<HTMLElement | null>(null);
const unifiedScroll = ref<HTMLElement | null>(null);
const connectorSvg = ref<SVGSVGElement | null>(null);
const connectorRail = ref<HTMLElement | null>(null);
const scrollHost = ref<HTMLElement | null>(null);
let connectorResizeObs: ResizeObserver | null = null;
let resizingSidebar = false;

const filteredFiles = computed(() => {
  const q = fileFilter.value.trim().toLowerCase();
  if (!q) return files.value;
  return files.value.filter(
    (f) =>
      f.relativePath.toLowerCase().includes(q) ||
      f.name.toLowerCase().includes(q) ||
      f.path.toLowerCase().includes(q),
  );
});

const selectedFile = computed(() => files.value.find((f) => f.path === selectedPath.value) || null);

const fileStatsText = computed(() => {
  const total = files.value.length;
  const adds = files.value.reduce((s, f) => s + (f.additions || 0), 0);
  const dels = files.value.reduce((s, f) => s + (f.deletions || 0), 0);
  return `${total} 个文件 · +${adds} / −${dels}`;
});

const typographyStyle = computed(() => {
  const family = FONT_STACKS[fontFamily.value] || FONT_STACKS[DEFAULT_FONT_FAMILY];
  const size = fontSize.value;
  return {
    "--diff-font-family": family,
    "--diff-font-size": `${size}px`,
    "--diff-line-height": `${Math.round(size * 1.45)}px`,
    "--sidebar-width": `${sidebarWidth.value}px`,
  } as Record<string, string>;
});

const rootLabel = computed(() =>
  props.title || (props.revision ? `${props.rootPath} @ r${props.revision}` : props.rootPath) || "DIFF",
);

function persistPrefs() {
  writePref("sf.diff.mode", mode.value);
  writePref("sf.diff.syncScroll", syncScroll.value ? "1" : "0");
  writePref("sf.diff.collapseUnchanged", collapseUnchanged.value ? "1" : "0");
  writePref("sf.diff.showLineNo", showLineNo.value ? "1" : "0");
  writePref("sf.diff.showPath", showPath.value ? "1" : "0");
  writePref("sf.diff.fontFamily", fontFamily.value);
  writePref("sf.diff.fontSize", String(fontSize.value));
  writePref("sf.diff.sidebarWidth", String(sidebarWidth.value));
}

function highlightSourceToLineHtml(text: string, language: string): string[] {
  const lines = text.split("\n");
  if (text.endsWith("\n")) {
    // keep consistent with diffLines splitting
  }
  const lang = resolveHighlightLang(language);
  if (!lang) {
    return lines.map((line) => escapeHtml(line));
  }
  try {
    const highlighted = highlightCode(text, language);
    // highlightCode already escapes when language is unsupported
    if (!highlighted.includes("<span") && highlighted === escapeHtml(text)) {
      return lines.map((line) => escapeHtml(line));
    }
    return splitHighlightedHtmlLinesWithTags(highlighted, lines.length);
  } catch {
    return lines.map((line) => escapeHtml(line));
  }
}

function splitHighlightedHtmlLinesWithTags(html: string, expectedCount: number): string[] {
  const lines: string[] = [];
  let current = "";
  const openStack: string[] = [];
  let i = 0;
  while (i < html.length) {
    if (html[i] === "<") {
      const end = html.indexOf(">", i);
      if (end < 0) {
        current += escapeHtml(html.slice(i));
        break;
      }
      const tag = html.slice(i, end + 1);
      current += tag;
      if (tag.startsWith("</")) {
        openStack.pop();
      } else if (!tag.endsWith("/>") && !tag.startsWith("<!")) {
        const m = tag.match(/^<([a-zA-Z0-9-]+)/);
        if (m) openStack.push(m[0] + (tag.includes(" ") ? tag.slice(m[0].length, tag.length - 1) + ">" : ">"));
        // simpler: track raw open tags
        openStack[openStack.length - 1] = tag.replace(/\/?>$/, ">");
      }
      i = end + 1;
      continue;
    }
    if (html[i] === "\n") {
      // close open tags then reopen on next line
      let closer = "";
      let opener = "";
      for (let k = openStack.length - 1; k >= 0; k -= 1) {
        const om = openStack[k].match(/^<([a-zA-Z0-9-]+)/);
        if (om) closer += `</${om[1]}>`;
      }
      for (const t of openStack) opener += t;
      lines.push(current + closer);
      current = opener;
      i += 1;
      continue;
    }
    current += html[i];
    i += 1;
  }
  lines.push(current);
  while (lines.length < expectedCount) lines.push("");
  if (lines.length > expectedCount) {
    // merge overflow into last
    const head = lines.slice(0, expectedCount - 1);
    const tail = lines.slice(expectedCount - 1).join("\n");
    return [...head, tail];
  }
  return lines;
}

function buildLineHighlightMaps(content: DiffFileContent, built: BuiltDiff) {
  const oldLines = content.oldText.split("\n");
  if (content.oldText.endsWith("\n") && oldLines[oldLines.length - 1] === "") oldLines.pop();
  const newLines = content.newText.split("\n");
  if (content.newText.endsWith("\n") && newLines[newLines.length - 1] === "") newLines.pop();

  // rebuild source from unified for accurate line map
  const oldText = content.oldText;
  const newText = content.newText;
  const oldHtmlLines = highlightSourceToLineHtml(oldText, content.language);
  const newHtmlLines = highlightSourceToLineHtml(newText, content.language);
  const oldMap = new Map<number, string>();
  const newMap = new Map<number, string>();
  for (let i = 0; i < oldHtmlLines.length; i += 1) oldMap.set(i + 1, oldHtmlLines[i]);
  for (let i = 0; i < newHtmlLines.length; i += 1) newMap.set(i + 1, newHtmlLines[i]);
  return { oldMap, newMap, built };
}

function codeHtml(maps: { oldMap: Map<number, string>; newMap: Map<number, string> }, side: "old" | "new", lineNo: number | null | undefined, fallback: string) {
  if (lineNo == null) return escapeHtml(fallback ?? "");
  const map = side === "old" ? maps.oldMap : maps.newMap;
  return map.get(lineNo) ?? escapeHtml(fallback ?? "");
}

async function loadFiles() {
  const token = ++loadToken;
  statsToken += 1; // 取消旧的后台统计
  contentCache.clear();
  loading.value = true;
  error.value = "";
  try {
    // 历史提交：优先使用外部传入的该次提交完整文件列表
    const list =
      props.revision && props.revisionFiles && props.revisionFiles.length
        ? props.revisionFiles.map((f) => ({ ...f }))
        : await api.svnDiffFiles(props.rootPath);
    if (token !== loadToken) return;

    // 排除目录 / 二进制扩展等无法文本 Diff 的项
    const diffable = filterDiffableFiles(list);
    // 先立刻展示文件列表（不预拉全部内容），避免 N 个文件串行 svn cat 卡死
    const baseList: Array<DiffFileInfo & { additions: number; deletions: number }> = diffable.map((item) => ({
      ...item,
      additions: item.additions || 0,
      deletions: item.deletions || 0,
    }));
    files.value = baseList;
    loading.value = false;

    if (baseList.length) {
      const preferred =
        (props.initialPath && baseList.find((f) => f.path === props.initialPath)?.path) ||
        baseList[0].path;
      // 列表 +/- 用一次 svn diff 解析（无需 cat）；内容仍懒加载
      const statsPromise = loadLineStatsWithoutCat(token);
      await selectFile(preferred, true);
      if (token !== loadToken) return;
      await statsPromise;
    } else {
      selectedPath.value = null;
      fileContent.value = null;
      builtDiff.value = null;
      if (list.length) {
        error.value = "本次变更仅包含无法文本对比的文件（如图片、Office、压缩包等）";
      }
    }
  } catch (e: any) {
    if (token !== loadToken) return;
    error.value = e?.message || String(e) || "加载 DIFF 失败";
    files.value = [];
  } finally {
    if (token === loadToken) loading.value = false;
  }
}

function normalizeDiffPath(p: string) {
  return (p || "").replace(/\\/g, "/").replace(/\/+$/, "");
}

function matchStatForFile(
  filePath: string,
  relativePath: string,
  stats: Array<{ path: string; relativePath: string; name?: string; additions: number; deletions: number; binary: boolean }>,
) {
  const fp = normalizeDiffPath(filePath);
  const rel = normalizeDiffPath(relativePath);
  const base = fp.split("/").pop() || "";
  return (
    stats.find((s) => normalizeDiffPath(s.path) === fp) ||
    stats.find((s) => {
      const sp = normalizeDiffPath(s.path);
      return sp.endsWith("/" + rel) || sp.endsWith(rel) || fp.endsWith("/" + normalizeDiffPath(s.relativePath));
    }) ||
    stats.find((s) => normalizeDiffPath(s.relativePath) === rel) ||
    (base
      ? stats.find(
          (s) =>
            normalizeDiffPath(s.path).endsWith("/" + base) ||
            (s.name || "").toLowerCase() === base.toLowerCase(),
        )
      : undefined)
  );
}

function applyLineStats(
  stats: Array<{ path: string; relativePath: string; name: string; additions: number; deletions: number; binary: boolean }>,
) {
  if (!stats.length) return;
  const next = files.value.map((f) => {
    const hit = matchStatForFile(f.path, f.relativePath || "", stats);
    if (!hit) return f;
    if (hit.binary) {
      return { ...f, binary: true, additions: 0, deletions: 0 };
    }
    return {
      ...f,
      additions: hit.additions || 0,
      deletions: hit.deletions || 0,
    };
  });
  // 去掉 diff 判定为二进制的项
  const selected = selectedPath.value;
  files.value = next.filter((f) => !f.binary && !isUnsupportedDiffPath(f.path, { binary: f.binary, isDir: f.isDir }));
  if (selected && !files.value.some((f) => f.path === selected)) {
    selectedPath.value = files.value[0]?.path || null;
  }
}

async function loadLineStatsWithoutCat(parentToken: number) {
  try {
    const stats = props.revision
      ? await api.svnRevisionDiffStats(props.rootPath, props.revision)
      : await api.svnWorkingDiffStats(props.rootPath);
    if (parentToken !== loadToken) return;
    applyLineStats(stats || []);
  } catch {
    // 统计失败不影响查看内容
  }
}

async function selectFile(path: string, force = false) {
  if (!force && selectedPath.value === path && builtDiff.value) return;
  selectedPath.value = path;
  loadingFile.value = true;
  error.value = "";
  expandedHunks.value = new Set();
  currentDiffIndex.value = -1;
  try {
    const cacheKey = contentCacheKey(path);
    let content = contentCache.get(cacheKey);
    if (!content) {
      content = props.revision
        ? await api.svnRevisionDiffFileContent(
            path,
            props.revision,
            files.value.find((f) => f.path === path)?.status || props.revisionAction,
          )
        : await api.svnDiffFileContent(path);
      // 仅缓存可展示文本，避免占内存过大的二进制
      if (!content.binary && !(content.message && /过大|二进制/.test(content.message || ""))) {
        contentCache.set(cacheKey, content);
      }
    }
    fileContent.value = content;
    // 不支持文本 Diff 的文件不保留在列表中
    if (
      content.binary ||
      (content.message && /二进制|过大|无法展示|目录无法/.test(content.message)) ||
      isUnsupportedDiffPath(path, { binary: content.binary })
    ) {
      const next = removeUnsupportedFile(path);
      builtDiff.value = null;
      fileContent.value = null;
      if (next) {
        await selectFile(next, true);
        return;
      }
      error.value = "没有可展示的文本差异文件";
      await nextTick();
      collectAnchors();
      updateDiffConnectors();
      return;
    }

    builtDiff.value = buildLineDiff(content.oldText, content.newText);
    const idx = files.value.findIndex((f) => f.path === path);
    if (idx >= 0 && builtDiff.value) {
      files.value[idx] = {
        ...files.value[idx],
        additions: builtDiff.value.stats.additions,
        deletions: builtDiff.value.stats.deletions,
        binary: false,
      };
    }
    await nextTick();
    collectAnchors();
    updateDiffConnectors();
  } catch (e: any) {
    error.value = e?.message || String(e) || "加载文件差异失败";
    fileContent.value = null;
    builtDiff.value = null;
  } finally {
    loadingFile.value = false;
  }
}

/** 从变更列表移除不支持 Diff 的文件，返回下一个可选项路径 */
function removeUnsupportedFile(path: string): string | null {
  const idx = files.value.findIndex((f) => f.path === path);
  if (idx < 0) {
    return files.value[0]?.path || null;
  }
  const next = files.value[idx + 1]?.path || files.value[idx - 1]?.path || null;
  files.value = files.value.filter((f) => f.path !== path);
  if (selectedPath.value === path) {
    selectedPath.value = next;
  }
  return next;
}

const highlightMaps = computed(() => {
  if (!fileContent.value || !builtDiff.value) return null;
  return buildLineHighlightMaps(fileContent.value, builtDiff.value);
});

const unifiedBlocks = computed(() => {
  if (!builtDiff.value) return [];
  const rows = builtDiff.value.unified;
  const collapsed = collapseRows(rows, (r) => r.type, collapseUnchanged.value);
  const blockIds = assignDiffBlockIds(rows, (r) => r.type);
  const out: Array<any> = [];
  for (const block of collapsed) {
    if (block.kind === "hunk") {
      const key = `${block.from}-${block.to}`;
      if (expandedHunks.value.has(key)) {
        for (let i = block.from; i < block.to; i += 1) {
          out.push({ kind: "row", row: rows[i], index: i, blockId: blockIds[i] });
        }
      } else {
        out.push(block);
      }
    } else {
      const index = rows.indexOf(block.row as UnifiedRow);
      out.push({ kind: "row", row: block.row, index, blockId: index >= 0 ? blockIds[index] : null });
    }
  }
  // fix indexes stably
  let p = 0;
  for (const item of out) {
    if (item.kind !== "row") continue;
    if (typeof item.index === "number" && item.index >= 0) {
      p = item.index + 1;
      continue;
    }
    while (p < rows.length && rows[p] !== item.row) p += 1;
    if (p < rows.length) {
      item.index = p;
      item.blockId = blockIds[p];
      p += 1;
    }
  }
  return out;
});

const splitBlocks = computed(() => {
  if (!builtDiff.value) return [];
  const rows = builtDiff.value.sideBySide;
  const collapsed = collapseRows(rows, (r) => r.type, collapseUnchanged.value);
  const blockIds = assignDiffBlockIds(rows, (r) => r.type);
  const out: Array<any> = [];
  for (const block of collapsed) {
    if (block.kind === "hunk") {
      const key = `${block.from}-${block.to}`;
      if (expandedHunks.value.has(key)) {
        for (let i = block.from; i < block.to; i += 1) {
          out.push({ kind: "row", row: rows[i], index: i, blockId: blockIds[i] });
        }
      } else {
        out.push(block);
      }
    } else {
      out.push({ kind: "row", row: block.row, index: -1, blockId: null });
    }
  }
  let p = 0;
  for (const item of out) {
    if (item.kind !== "row") continue;
    if (typeof item.index === "number" && item.index >= 0) {
      p = item.index + 1;
      continue;
    }
    while (p < rows.length && rows[p] !== item.row) p += 1;
    if (p < rows.length) {
      item.index = p;
      item.blockId = blockIds[p];
      p += 1;
    }
  }
  return out;
});

function expandHunk(from: number, to: number) {
  const next = new Set(expandedHunks.value);
  next.add(`${from}-${to}`);
  expandedHunks.value = next;
  nextTick(() => {
    collectAnchors();
    updateDiffConnectors();
  });
}

function collectAnchors() {
  nextTick(() => {
    const root = diffRoot.value;
    if (!root) {
      diffAnchors.value = [];
      currentDiffIndex.value = -1;
      return;
    }
    const nodes = Array.from(root.querySelectorAll<HTMLElement>("tr.row-diff-anchor[data-diff-block]"));
    const seen = new Set<string>();
    const anchors: Array<{ id: number; el: HTMLElement }> = [];
    for (const el of nodes) {
      const id = el.getAttribute("data-diff-block");
      if (!id || seen.has(id)) continue;
      seen.add(id);
      anchors.push({ id: Number(id), el });
    }
    diffAnchors.value = anchors;
    if (!anchors.length) currentDiffIndex.value = -1;
    else if (currentDiffIndex.value < 0 || currentDiffIndex.value >= anchors.length) currentDiffIndex.value = 0;
    highlightCurrentBlock();
  });
}

function highlightCurrentBlock() {
  const root = diffRoot.value;
  if (!root) return;
  root.querySelectorAll("tr.current-block").forEach((n) => n.classList.remove("current-block"));
  const anchor = diffAnchors.value[currentDiffIndex.value];
  if (!anchor) return;
  root
    .querySelectorAll(`tr.row-diff-block[data-diff-block="${anchor.id}"]`)
    .forEach((n) => n.classList.add("current-block"));
}

function jumpDiff(dir: number) {
  if (!diffAnchors.value.length) return;
  let idx = currentDiffIndex.value;
  if (idx < 0) idx = dir > 0 ? 0 : diffAnchors.value.length - 1;
  else idx = (idx + dir + diffAnchors.value.length) % diffAnchors.value.length;
  currentDiffIndex.value = idx;
  const anchor = diffAnchors.value[idx];
  if (anchor?.el) {
    anchor.el.scrollIntoView({ block: "center", behavior: "smooth" });
  }
  highlightCurrentBlock();
  updateDiffConnectors();
}

function onScrollSync(source: "left" | "right") {
  if (!syncScroll.value || mode.value !== "split") {
    updateDiffConnectors();
    return;
  }
  if (syncingScroll.value) return;
  const left = leftScroll.value;
  const right = rightScroll.value;
  if (!left || !right) return;
  syncingScroll.value = true;
  if (source === "left") {
    right.scrollTop = left.scrollTop;
    right.scrollLeft = left.scrollLeft;
  } else {
    left.scrollTop = right.scrollTop;
    left.scrollLeft = right.scrollLeft;
  }
  requestAnimationFrame(() => {
    syncingScroll.value = false;
    updateDiffConnectors();
  });
}

function updateDiffConnectors() {
  if (mode.value !== "split") return;
  const host = scrollHost.value;
  const svg = connectorSvg.value;
  const left = leftScroll.value;
  const right = rightScroll.value;
  const rail = connectorRail.value;
  if (!host || !svg || !left || !right) return;

  const hostRect = host.getBoundingClientRect();
  const railRect = rail ? rail.getBoundingClientRect() : hostRect;
  const width = Math.max(0, rail ? rail.clientWidth : 56);
  const height = Math.max(0, host.clientHeight);
  svg.setAttribute("width", String(width));
  svg.setAttribute("height", String(height));
  svg.setAttribute("viewBox", `0 0 ${width} ${height}`);

  // 按差异块（连续变更块）而不是单行画连接带
  const leftRows = Array.from(left.querySelectorAll<HTMLElement>("tr.row-diff-block[data-diff-block]"));
  const ids: string[] = [];
  const seen = new Set<string>();
  for (const row of leftRows) {
    const id = row.getAttribute("data-diff-block");
    if (!id || seen.has(id)) continue;
    seen.add(id);
    ids.push(id);
  }

  const currentId =
    currentDiffIndex.value >= 0 && diffAnchors.value[currentDiffIndex.value]
      ? String(diffAnchors.value[currentDiffIndex.value].id)
      : null;

  const parts: string[] = [];
  for (const id of ids) {
    const lRows = Array.from(
      left.querySelectorAll<HTMLElement>(`tr.row-diff-block[data-diff-block="${id}"]`),
    );
    const rRows = Array.from(
      right.querySelectorAll<HTMLElement>(`tr.row-diff-block[data-diff-block="${id}"]`),
    );
    if (!lRows.length || !rRows.length) continue;

    const lFirst = lRows[0].getBoundingClientRect();
    const lLast = lRows[lRows.length - 1].getBoundingClientRect();
    const rFirst = rRows[0].getBoundingClientRect();
    const rLast = rRows[rRows.length - 1].getBoundingClientRect();

    const bandTop = Math.min(lFirst.top, rFirst.top);
    const bandBottom = Math.max(lLast.bottom, rLast.bottom);
    if (bandBottom < hostRect.top - 40 || bandTop > hostRect.bottom + 40) continue;

    const pad = 3;
    const x1 = pad;
    const x2 = Math.max(pad + 8, width - pad);
    const y1t = lFirst.top - railRect.top;
    const y1b = lLast.bottom - railRect.top;
    const y2t = rFirst.top - railRect.top;
    const y2b = rLast.bottom - railRect.top;
    const span = Math.max(24, x2 - x1);
    const c1 = x1 + span * 0.45;
    const c2 = x2 - span * 0.45;

    let kind = "mod";
    if (lRows[0].classList.contains("block-type-add") || lRows[0].classList.contains("row-add")) kind = "add";
    if (lRows[0].classList.contains("block-type-del") || lRows[0].classList.contains("row-del")) kind = "del";
    if (lRows[0].classList.contains("block-type-mod") || lRows[0].classList.contains("row-mod")) kind = "mod";
    const hasDel = lRows.some((r) => r.classList.contains("row-del") || r.classList.contains("row-mod"));
    const hasAdd = rRows.some((r) => r.classList.contains("row-add") || r.classList.contains("row-mod"));
    if (hasDel && hasAdd) kind = "mod";
    else if (hasAdd && !hasDel) kind = "add";
    else if (hasDel && !hasAdd) kind = "del";

    const active = currentId === String(id) ? " is-active" : "";
    const d = [
      `M ${x1.toFixed(1)} ${y1t.toFixed(1)}`,
      `C ${c1.toFixed(1)} ${y1t.toFixed(1)}, ${c2.toFixed(1)} ${y2t.toFixed(1)}, ${x2.toFixed(1)} ${y2t.toFixed(1)}`,
      `L ${x2.toFixed(1)} ${y2b.toFixed(1)}`,
      `C ${c2.toFixed(1)} ${y2b.toFixed(1)}, ${c1.toFixed(1)} ${y1b.toFixed(1)}, ${x1.toFixed(1)} ${y1b.toFixed(1)}`,
      "Z",
    ].join(" ");
    const topEdge = [
      `M ${x1.toFixed(1)} ${y1t.toFixed(1)}`,
      `C ${c1.toFixed(1)} ${y1t.toFixed(1)}, ${c2.toFixed(1)} ${y2t.toFixed(1)}, ${x2.toFixed(1)} ${y2t.toFixed(1)}`,
    ].join(" ");
    const bottomEdge = [
      `M ${x1.toFixed(1)} ${y1b.toFixed(1)}`,
      `C ${c1.toFixed(1)} ${y1b.toFixed(1)}, ${c2.toFixed(1)} ${y2b.toFixed(1)}, ${x2.toFixed(1)} ${y2b.toFixed(1)}`,
    ].join(" ");
    parts.push(
      `<path class="diff-connector kind-${kind}${active}" data-diff-block="${id}" d="${d}"></path>` +
        `<path class="diff-connector-edge kind-${kind}${active}" data-diff-block="${id}" d="${topEdge}"></path>` +
        `<path class="diff-connector-edge kind-${kind}${active}" data-diff-block="${id}" d="${bottomEdge}"></path>`,
    );
  }
  svg.innerHTML = parts.join("");
}

function bindConnectorObserver() {
  if (connectorResizeObs) {
    try {
      connectorResizeObs.disconnect();
    } catch {
      // ignore
    }
    connectorResizeObs = null;
  }
  const host = scrollHost.value;
  if (!host) return;
  const ro = new ResizeObserver(() => updateDiffConnectors());
  ro.observe(host);
  if (leftScroll.value) ro.observe(leftScroll.value);
  if (rightScroll.value) ro.observe(rightScroll.value);
  connectorResizeObs = ro;
}

function onSidebarResizeStart(e: MouseEvent) {
  e.preventDefault();
  resizingSidebar = true;
  document.body.classList.add("is-resizing-sidebar");
  const startX = e.clientX;
  const startW = sidebarWidth.value;
  const onMove = (ev: MouseEvent) => {
    if (!resizingSidebar) return;
    sidebarWidth.value = clampSidebarWidth(startW + (ev.clientX - startX));
  };
  const onUp = () => {
    resizingSidebar = false;
    document.body.classList.remove("is-resizing-sidebar");
    persistPrefs();
    window.removeEventListener("mousemove", onMove);
    window.removeEventListener("mouseup", onUp);
  };
  window.addEventListener("mousemove", onMove);
  window.addEventListener("mouseup", onUp);
}

function rowEdge(blockIds: Array<number | null>, index: number) {
  return blockEdgeClass(blockIds, index);
}

function sideClass(type: string, rowType: string) {
  if (type === "del") return "row-del";
  if (type === "add") return "row-add";
  if (type === "empty") return "row-empty";
  if (rowType === "mod") return "row-mod";
  return "row-ctx";
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === "Escape") {
    emit("close");
    return;
  }
  if (e.key === "F7" && e.shiftKey) {
    e.preventDefault();
    jumpDiff(-1);
  } else if (e.key === "F7") {
    e.preventDefault();
    jumpDiff(1);
  }
}

watch([mode, collapseUnchanged, showLineNo], async () => {
  persistPrefs();
  expandedHunks.value = new Set();
  await nextTick();
  collectAnchors();
  bindConnectorObserver();
  updateDiffConnectors();
});

watch([syncScroll, showPath, fontFamily, fontSize], () => {
  persistPrefs();
});

watch(
  () => [props.rootPath, props.revision, props.revisionFiles, props.initialPath],
  () => {
    void loadFiles();
  },
);

onMounted(() => {
  window.addEventListener("keydown", onKeydown);
  window.addEventListener("resize", updateDiffConnectors);
  void loadFiles();
});

onUnmounted(() => {
  window.removeEventListener("keydown", onKeydown);
  window.removeEventListener("resize", updateDiffConnectors);
  if (connectorResizeObs) {
    try {
      connectorResizeObs.disconnect();
    } catch {
      // ignore
    }
  }
  document.body.classList.remove("is-resizing-sidebar");
});

watch(builtDiff, async () => {
  await nextTick();
  bindConnectorObserver();
  collectAnchors();
  updateDiffConnectors();
});
</script>

<template>
  <div class="diff-viewer" :style="typographyStyle">
    <header class="dv-topbar">
      <div class="dv-topbar-row dv-topbar-main">
        <div class="dv-brand">
          <span class="dv-brand-mark">◈</span>
          <div class="dv-brand-text">
            <strong>{{ rootLabel }}</strong>
            <span class="dv-muted">{{ revision ? `历史修订 r${revision}` : "BASE · 工作副本" }}</span>
          </div>
        </div>
        <div class="dv-top-actions">
          <span class="dv-file-stats">{{ fileStatsText }}</span>
          <button type="button" class="dv-btn secondary" :disabled="loading" @click="loadFiles">刷新</button>
          <button type="button" class="dv-btn" @click="emit('close')">关闭</button>
        </div>
      </div>

      <div class="dv-topbar-row dv-topbar-tools">
        <div class="dv-toolbar">
          <div class="dv-seg" role="group" aria-label="查看模式">
            <button
              type="button"
              class="dv-seg-btn"
              :class="{ active: mode === 'split' }"
              @click="mode = 'split'"
            >
              并排
            </button>
            <button
              type="button"
              class="dv-seg-btn"
              :class="{ active: mode === 'unified' }"
              @click="mode = 'unified'"
            >
              统一
            </button>
          </div>

          <label class="dv-toggle" title="左右同步滚动">
            <input v-model="syncScroll" type="checkbox" />
            <span>同步滚动</span>
          </label>
          <label class="dv-toggle" title="收起未更改片段">
            <input v-model="collapseUnchanged" type="checkbox" />
            <span>收起未更改</span>
          </label>
          <label class="dv-check">
            <input v-model="showLineNo" type="checkbox" />
            <span>行号</span>
          </label>
          <label class="dv-check">
            <input v-model="showPath" type="checkbox" />
            <span>文件路径</span>
          </label>

          <div class="dv-select-field" title="代码字体">
            <span class="dv-field-label">字体</span>
            <select v-model="fontFamily" class="dv-select">
              <option v-for="name in Object.keys(FONT_STACKS)" :key="name" :value="name">{{ name }}</option>
            </select>
          </div>
          <div class="dv-select-field" title="代码字号">
            <span class="dv-field-label">字号</span>
            <select v-model.number="fontSize" class="dv-select dv-select-sm">
              <option v-for="n in 11" :key="n" :value="n + 9">{{ n + 9 }}</option>
            </select>
          </div>

          <div class="dv-nav-group">
            <button type="button" class="dv-btn secondary dv-btn-mini" :disabled="!diffAnchors.length" @click="jumpDiff(-1)">
              上一处
            </button>
            <button type="button" class="dv-btn secondary dv-btn-mini" :disabled="!diffAnchors.length" @click="jumpDiff(1)">
              下一处
            </button>
          </div>
        </div>
      </div>
    </header>

    <main class="dv-main">
      <aside class="dv-sidebar">
        <div class="dv-sidebar-header">
          <div class="dv-sidebar-title">变更文件</div>
          <input v-model="fileFilter" class="dv-filter" type="search" placeholder="过滤文件…" />
        </div>
        <div v-if="loading" class="dv-empty">加载中…</div>
        <div v-else-if="!filteredFiles.length" class="dv-empty">没有可展示的差异文件</div>
        <div v-else class="dv-file-list">
          <button
            v-for="f in filteredFiles"
            :key="f.path"
            type="button"
            class="dv-file-item"
            :class="{ active: f.path === selectedPath }"
            @click="selectFile(f.path)"
          >
            <span class="dv-icon" :class="statusClass(f.statusLabel || f.status)">{{ statusIcon(f.statusLabel || f.status) }}</span>
            <span class="dv-name">
              <template v-if="showPath">
                <span class="dv-dir">{{ splitName(f.relativePath || f.path).dir }}</span>
                <span>{{ splitName(f.relativePath || f.path).name }}</span>
              </template>
              <template v-else>{{ f.name }}</template>
            </span>
            <span class="dv-counts">
              <span class="a">+{{ f.additions || 0 }}</span>
              <span class="d">−{{ f.deletions || 0 }}</span>
            </span>
          </button>
        </div>
      </aside>

      <div class="dv-sidebar-resizer" title="拖拽调整宽度" @mousedown="onSidebarResizeStart" />

      <section class="dv-content">
        <div v-if="selectedFile" class="dv-file-header">
          <div class="dv-file-header-left">
            <span class="dv-status-badge" :class="statusClass(selectedFile.statusLabel || selectedFile.status)">
              {{ statusLabel(selectedFile.status, selectedFile.statusLabel) }}
            </span>
            <span class="dv-file-path">{{ selectedFile.relativePath || selectedFile.path }}</span>
          </div>
          <div class="dv-diff-stats">
            <span class="a">+{{ selectedFile.additions || 0 }}</span>
            <span class="d">−{{ selectedFile.deletions || 0 }}</span>
          </div>
        </div>

        <div v-if="error" class="dv-error">{{ error }}</div>
        <div v-else-if="loading || loadingFile" class="dv-welcome">
          <div class="dv-welcome-card">
            <h1>正在加载差异…</h1>
          </div>
        </div>
        <div v-else-if="!selectedFile" class="dv-welcome">
          <div class="dv-welcome-card">
            <h1>选择左侧文件查看差异</h1>
            <p>历史模式对比「上一修订」与「该次提交」；本地模式对比「BASE」与「工作副本」。</p>
          </div>
        </div>
        <div v-else-if="fileContent?.binary || fileContent?.message" class="dv-binary-note">
          {{ fileContent.message || "该文件为二进制文件，无法展示文本 Diff。" }}
        </div>
        <div v-else-if="builtDiff" ref="diffRoot" class="dv-diff-root">
          <!-- unified -->
          <template v-if="mode === 'unified'">
            <div class="dv-pane-labels unified">
              <div class="dv-pane-label">
                <strong>统一 Diff</strong>
                {{ fileContent?.relativePath || selectedFile.path }}
              </div>
            </div>
            <div class="dv-scroll-host">
              <div ref="unifiedScroll" class="dv-scroll">
                <table class="dv-table" :class="{ 'hide-ln': !showLineNo }">
                  <tbody>
                    <template v-for="(block, bi) in unifiedBlocks" :key="'u-' + bi">
                      <tr
                        v-if="block.kind === 'hunk'"
                        class="row-hunk"
                        @click="expandHunk(block.from, block.to)"
                      >
                        <td class="ln"></td>
                        <td class="ln"></td>
                        <td class="gutter">⋮</td>
                        <td class="code">⋯ 收起了 {{ block.hidden }} 行未更改内容，点击展开</td>
                      </tr>
                      <tr
                        v-else
                        :class="[
                          block.row.type === 'add' ? 'row-add' : block.row.type === 'del' ? 'row-del' : 'row-ctx',
                          block.blockId != null ? 'row-diff-anchor row-diff-block' : '',
                          block.blockId != null ? rowEdge(assignDiffBlockIds(builtDiff.unified, (r) => r.type), block.index) : '',
                          block.blockId != null ? blockTypeClass(block.row.type) : '',
                        ]"
                        :data-diff-type="block.row.type"
                        :data-diff-block="block.blockId != null ? String(block.blockId) : undefined"
                      >
                        <td class="ln">{{ block.row.oldLine ?? '' }}</td>
                        <td class="ln">{{ block.row.newLine ?? '' }}</td>
                        <td class="gutter">{{ block.row.type === 'add' ? '+' : block.row.type === 'del' ? '−' : ' ' }}</td>
                        <td
                          class="code"
                          v-html="
                            highlightMaps
                              ? codeHtml(
                                  highlightMaps,
                                  block.row.type === 'del' ? 'old' : 'new',
                                  block.row.type === 'del' ? block.row.oldLine : block.row.newLine,
                                  block.row.text,
                                )
                              : escapeHtml(block.row.text)
                          "
                        ></td>
                      </tr>
                    </template>
                  </tbody>
                </table>
              </div>
            </div>
          </template>

          <!-- split -->
          <template v-else>
            <div class="dv-pane-labels split-labels">
              <div class="dv-pane-label">
                <strong>{{ revision ? `r${Math.max(1, Number(revision) - 1)}` : "BASE" }}</strong>
                {{ fileContent?.relativePath || selectedFile.path }}
              </div>
              <div class="dv-pane-label-gap" aria-hidden="true"></div>
              <div class="dv-pane-label">
                <strong>{{ revision ? `r${revision}` : "工作副本" }}</strong>
                {{ fileContent?.relativePath || selectedFile.path }}
              </div>
            </div>
            <div ref="scrollHost" class="dv-scroll-host split">
              <div ref="leftScroll" class="dv-scroll" @scroll="onScrollSync('left')">
                <table class="dv-table" :class="{ 'hide-ln': !showLineNo }">
                  <tbody>
                    <template v-for="(block, bi) in splitBlocks" :key="'sl-' + bi">
                      <tr
                        v-if="block.kind === 'hunk'"
                        class="row-hunk"
                        @click="expandHunk(block.from, block.to)"
                      >
                        <td class="ln"></td>
                        <td class="gutter">⋮</td>
                        <td class="code">⋯ 收起了 {{ block.hidden }} 行未更改内容，点击展开</td>
                      </tr>
                      <tr
                        v-else
                        :class="[
                          sideClass(block.row.left?.type, block.row.type),
                          block.blockId != null ? 'row-diff-anchor row-diff-block' : '',
                          block.blockId != null ? rowEdge(assignDiffBlockIds(builtDiff.sideBySide, (r) => r.type), block.index) : '',
                          block.blockId != null ? blockTypeClass(block.row.type) : '',
                        ]"
                        :data-diff-type="block.row.type"
                        :data-diff-block="block.blockId != null ? String(block.blockId) : undefined"
                      >
                        <td class="ln">{{ block.row.left?.line ?? '' }}</td>
                        <td class="gutter">
                          {{
                            block.row.left?.type === 'del'
                              ? '−'
                              : block.row.left?.type === 'add'
                                ? '+'
                                : block.row.type === 'mod'
                                  ? '~'
                                  : ' '
                          }}
                        </td>
                        <td
                          class="code"
                          v-html="
                            highlightMaps
                              ? codeHtml(highlightMaps, 'old', block.row.left?.line, block.row.left?.text ?? '')
                              : escapeHtml(block.row.left?.text ?? '')
                          "
                        ></td>
                      </tr>
                    </template>
                  </tbody>
                </table>
              </div>
              <div ref="connectorRail" class="dv-connector-rail" aria-hidden="true">
                <svg ref="connectorSvg" class="dv-connectors"></svg>
              </div>
              <div ref="rightScroll" class="dv-scroll" @scroll="onScrollSync('right')">
                <table class="dv-table" :class="{ 'hide-ln': !showLineNo }">
                  <tbody>
                    <template v-for="(block, bi) in splitBlocks" :key="'sr-' + bi">
                      <tr
                        v-if="block.kind === 'hunk'"
                        class="row-hunk"
                        @click="expandHunk(block.from, block.to)"
                      >
                        <td class="ln"></td>
                        <td class="gutter">⋮</td>
                        <td class="code">⋯ 收起了 {{ block.hidden }} 行未更改内容，点击展开</td>
                      </tr>
                      <tr
                        v-else
                        :class="[
                          sideClass(block.row.right?.type, block.row.type),
                          block.blockId != null ? 'row-diff-anchor row-diff-block' : '',
                          block.blockId != null ? rowEdge(assignDiffBlockIds(builtDiff.sideBySide, (r) => r.type), block.index) : '',
                          block.blockId != null ? blockTypeClass(block.row.type) : '',
                        ]"
                        :data-diff-type="block.row.type"
                        :data-diff-block="block.blockId != null ? String(block.blockId) : undefined"
                      >
                        <td class="ln">{{ block.row.right?.line ?? '' }}</td>
                        <td class="gutter">
                          {{
                            block.row.right?.type === 'add'
                              ? '+'
                              : block.row.right?.type === 'del'
                                ? '−'
                                : block.row.type === 'mod'
                                  ? '~'
                                  : ' '
                          }}
                        </td>
                        <td
                          class="code"
                          v-html="
                            highlightMaps
                              ? codeHtml(highlightMaps, 'new', block.row.right?.line, block.row.right?.text ?? '')
                              : escapeHtml(block.row.right?.text ?? '')
                          "
                        ></td>
                      </tr>
                    </template>
                  </tbody>
                </table>
              </div>
            </div>
          </template>
        </div>
      </section>
    </main>
  </div>
</template>
