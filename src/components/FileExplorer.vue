<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref } from "vue";
import type { FsEntry, ViewMode } from "../types";
import FileIcon from "./FileIcon.vue";
import { getSvnStatusMeta } from "../utils/materialIcon";

const props = defineProps<{
  entries: FsEntry[];
  selectedPaths: string[];
  viewMode: ViewMode;
  breadcrumb: { label: string; path: string }[];
  columnStacks: { path: string; entries: FsEntry[]; selected?: string | null }[];
  busy: boolean;
  workspacePath: string | null;
}>();

const emit = defineEmits<{
  select: [payload: { entry: FsEntry; additive: boolean; range: boolean }];
  selectPaths: [paths: string[]];
  open: [entry: FsEntry];
  navigate: [path: string];
  context: [payload: { entry: FsEntry; x: number; y: number }];
  changeView: [mode: ViewMode];
  refresh: [];
  update: [];
  commit: [];
  changes: [];
  history: [];
  copied: [path: string];
  copyFailed: [message: string];
}>();

const bodyRef = ref<HTMLElement | null>(null);
const selecting = ref(false);
const marquee = ref<{ left: number; top: number; width: number; height: number } | null>(null);
const suppressClickUntil = ref(0);

let dragStart: { x: number; y: number; scrollLeft: number; scrollTop: number; pointerId: number } | null = null;
let baseSelection: string[] = [];
let didDragSelect = false;
const MARQUEE_THRESHOLD = 8;
const DEFAULT_COLUMN_WIDTH = 260;
const MIN_COLUMN_WIDTH = 180;
const MAX_COLUMN_WIDTH = 720;

/** 分栏宽度：按栏路径记忆 */
const columnWidths = ref<Record<string, number>>({});
let resizingCol: { path: string; startX: number; startW: number } | null = null;

function columnWidth(path: string) {
  return columnWidths.value[path] || DEFAULT_COLUMN_WIDTH;
}

function onColumnResizeStart(path: string, e: PointerEvent) {
  e.preventDefault();
  e.stopPropagation();
  resizingCol = {
    path,
    startX: e.clientX,
    startW: columnWidth(path),
  };
  window.addEventListener("pointermove", onColumnResizeMove);
  window.addEventListener("pointerup", onColumnResizeEnd);
  window.addEventListener("pointercancel", onColumnResizeEnd);
  document.body.classList.add("col-resizing");
}

function onColumnResizeMove(e: PointerEvent) {
  if (!resizingCol) return;
  const dx = e.clientX - resizingCol.startX;
  const next = Math.min(MAX_COLUMN_WIDTH, Math.max(MIN_COLUMN_WIDTH, resizingCol.startW + dx));
  columnWidths.value = { ...columnWidths.value, [resizingCol.path]: next };
}

function onColumnResizeEnd() {
  resizingCol = null;
  window.removeEventListener("pointermove", onColumnResizeMove);
  window.removeEventListener("pointerup", onColumnResizeEnd);
  window.removeEventListener("pointercancel", onColumnResizeEnd);
  document.body.classList.remove("col-resizing");
}

const selectedSet = computed(() => new Set(props.selectedPaths));

function isSelected(path: string) {
  return selectedSet.value.has(path);
}

async function copyWorkspacePath() {
  const path = props.workspacePath;
  if (!path) return;
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(path);
    } else {
      const input = document.createElement("textarea");
      input.value = path;
      input.setAttribute("readonly", "true");
      input.style.position = "fixed";
      input.style.opacity = "0";
      document.body.appendChild(input);
      input.select();
      const ok = document.execCommand("copy");
      document.body.removeChild(input);
      if (!ok) throw new Error("复制失败");
    }
    emit("copied", path);
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    emit("copyFailed", msg || "复制失败");
  }
}

function formatSize(size: number, isDir: boolean) {
  if (isDir) return "—";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

function formatTime(ts?: number | null) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString();
}

function statusText(status?: string | null) {
  return getSvnStatusMeta(status);
}

function onItemClick(entry: FsEntry, e: MouseEvent) {
  if (Date.now() < suppressClickUntil.value) {
    e.preventDefault();
    e.stopPropagation();
    return;
  }
  emit("select", {
    entry,
    additive: e.metaKey || e.ctrlKey,
    range: e.shiftKey,
  });
}

function onContext(entry: FsEntry, e: MouseEvent) {
  e.preventDefault();
  e.stopPropagation();
  if (!isSelected(entry.path)) {
    emit("select", { entry, additive: false, range: false });
  }
  emit("context", { entry, x: e.clientX, y: e.clientY });
}

function onDbl(entry: FsEntry) {
  if (entry.isDir) emit("open", entry);
}

function entryEls(): HTMLElement[] {
  const root = bodyRef.value;
  if (!root) return [];
  return Array.from(root.querySelectorAll<HTMLElement>("[data-entry-path]"));
}

function rectsIntersect(
  a: { left: number; top: number; right: number; bottom: number },
  b: { left: number; top: number; right: number; bottom: number },
) {
  return !(a.right < b.left || a.left > b.right || a.bottom < b.top || a.top > b.bottom);
}

function collectPathsInMarquee(box: { left: number; top: number; right: number; bottom: number }) {
  const paths: string[] = [];
  for (const el of entryEls()) {
    const r = el.getBoundingClientRect();
    if (
      rectsIntersect(box, {
        left: r.left,
        top: r.top,
        right: r.right,
        bottom: r.bottom,
      })
    ) {
      const path = el.dataset.entryPath;
      if (path) paths.push(path);
    }
  }
  return paths;
}

function updateMarqueeSelection(clientX: number, clientY: number, additive: boolean) {
  if (!dragStart || !bodyRef.value) return;
  const bodyRect = bodyRef.value.getBoundingClientRect();
  const scrollLeft = bodyRef.value.scrollLeft;
  const scrollTop = bodyRef.value.scrollTop;

  // 起点相对 body 内容坐标
  const startX = dragStart.x - bodyRect.left + dragStart.scrollLeft;
  const startY = dragStart.y - bodyRect.top + dragStart.scrollTop;
  const curX = clientX - bodyRect.left + scrollLeft;
  const curY = clientY - bodyRect.top + scrollTop;

  const left = Math.min(startX, curX);
  const top = Math.min(startY, curY);
  const width = Math.abs(curX - startX);
  const height = Math.abs(curY - startY);

  marquee.value = { left, top, width, height };

  // 可见区域相交检测使用 viewport 坐标
  const box = {
    left: bodyRect.left + left - scrollLeft,
    top: bodyRect.top + top - scrollTop,
    right: bodyRect.left + left - scrollLeft + width,
    bottom: bodyRect.top + top - scrollTop + height,
  };
  const hit = collectPathsInMarquee(box);
  if (additive) {
    const set = new Set(baseSelection);
    for (const p of hit) set.add(p);
    emit("selectPaths", Array.from(set));
  } else {
    emit("selectPaths", hit);
  }
}

function clearNativeSelection() {
  const sel = window.getSelection?.();
  if (sel && sel.rangeCount) sel.removeAllRanges();
}

function onSelectStart(e: Event) {
  // 框选期间禁止浏览器原生文字选中
  if (selecting.value) {
    e.preventDefault();
  }
}

function onBodyPointerDown(e: PointerEvent) {
  if (e.button !== 0) return;
  if (props.busy || !props.breadcrumb.length) return;
  // 仅左键拖拽框选；不拦截条目自身 click / dblclick（由条目处理）
  const target = e.target as HTMLElement | null;
  if (target?.closest("button, input, textarea, a, .workspace-fullpath")) return;

  const body = bodyRef.value;
  if (!body) return;

  // 不要在 pointerdown 立刻 setPointerCapture，否则会打断 click/dblclick，
  // 导致双击进文件夹、分栏单击打开失效。
  selecting.value = true;
  didDragSelect = false;
  dragStart = {
    x: e.clientX,
    y: e.clientY,
    scrollLeft: body.scrollLeft,
    scrollTop: body.scrollTop,
    pointerId: e.pointerId,
  };
  baseSelection = e.metaKey || e.ctrlKey ? [...props.selectedPaths] : [];
  marquee.value = null;
  clearNativeSelection();

  window.addEventListener("pointermove", onWindowPointerMove);
  window.addEventListener("pointerup", onWindowPointerUp);
  window.addEventListener("pointercancel", onWindowPointerUp);
  window.addEventListener("selectstart", onSelectStart, true);
}

function onWindowPointerMove(e: PointerEvent) {
  if (!selecting.value || !dragStart) return;
  const dx = e.clientX - dragStart.x;
  const dy = e.clientY - dragStart.y;
  if (!didDragSelect && Math.hypot(dx, dy) < MARQUEE_THRESHOLD) return;

  if (!didDragSelect) {
    didDragSelect = true;
    // 确认进入框选后才捕获指针/拦截默认行为，避免影响单击/双击打开
    try {
      bodyRef.value?.setPointerCapture(dragStart.pointerId);
    } catch {
      // ignore
    }
    clearNativeSelection();
  }

  // 真正框选后阻止原生文字选择，只保留文件/文件夹选中
  e.preventDefault();
  clearNativeSelection();
  updateMarqueeSelection(e.clientX, e.clientY, e.metaKey || e.ctrlKey || baseSelection.length > 0);
}

async function onWindowPointerUp(e: PointerEvent) {
  if (!selecting.value) return;
  const wasDrag = didDragSelect;
  const pointerId = dragStart?.pointerId;
  selecting.value = false;
  marquee.value = null;
  dragStart = null;
  window.removeEventListener("pointermove", onWindowPointerMove);
  window.removeEventListener("pointerup", onWindowPointerUp);
  window.removeEventListener("pointercancel", onWindowPointerUp);
  window.removeEventListener("selectstart", onSelectStart, true);

  if (pointerId != null) {
    try {
      if (bodyRef.value?.hasPointerCapture?.(pointerId)) {
        bodyRef.value.releasePointerCapture(pointerId);
      }
    } catch {
      // ignore
    }
  }

  clearNativeSelection();

  if (wasDrag) {
    suppressClickUntil.value = Date.now() + 250;
    // 防止紧随其后的 click 覆盖框选
    await nextTick();
  } else {
    // 点空白处：清空选择（若点在条目上，条目 click 会重新选中）
    const target = e.target as HTMLElement | null;
    if (target && !target.closest("[data-entry-path]")) {
      emit("selectPaths", []);
    }
  }
}

onBeforeUnmount(() => {
  window.removeEventListener("pointermove", onWindowPointerMove);
  window.removeEventListener("pointerup", onWindowPointerUp);
  window.removeEventListener("pointercancel", onWindowPointerUp);
  window.removeEventListener("selectstart", onSelectStart, true);
  onColumnResizeEnd();
});
</script>

<template>
  <section class="panel center-main relative">
    <div v-if="busy" class="loading-overlay"><div class="spinner" /></div>

    <div class="file-header">
      <button
        v-if="workspacePath"
        type="button"
        class="workspace-fullpath"
        :title="'点击复制完整路径\n' + workspacePath"
        @click="copyWorkspacePath"
      >
        <span class="workspace-fullpath-label">路径</span>
        <span class="workspace-fullpath-text">{{ workspacePath }}</span>
        <span class="workspace-fullpath-hint">点击复制</span>
      </button>

      <div class="file-toolbar">
        <div class="breadcrumb">
          <template v-for="(item, idx) in breadcrumb" :key="item.path">
            <span v-if="idx > 0" class="sep">/</span>
            <button @click="emit('navigate', item.path)">{{ item.label }}</button>
          </template>
        </div>
        <div class="toolbar">
          <div class="svn-actions">
            <button class="btn" :disabled="busy || !workspacePath" title="更新 (⌘U)" @click="emit('update')">更新</button>
            <button class="btn btn-primary" :disabled="busy || !workspacePath" title="提交 (⌘↩)" @click="emit('commit')">提交</button>
            <button class="btn" :disabled="busy || !workspacePath" title="查看本地变更 (⌘⇧C)" @click="emit('changes')">变更</button>
            <button class="btn" :disabled="busy || !workspacePath" title="查看提交历史 (⌘⇧H)" @click="emit('history')">历史</button>
          </div>
          <div class="view-toggle">
            <button :class="{ active: viewMode === 'list' }" @click="emit('changeView', 'list')">列表</button>
            <button :class="{ active: viewMode === 'icons' }" @click="emit('changeView', 'icons')">图标</button>
            <button :class="{ active: viewMode === 'columns' }" @click="emit('changeView', 'columns')">分栏</button>
          </div>
          <button class="btn" :disabled="busy" title="刷新 (⌘R)" @click="emit('refresh')">刷新</button>
        </div>
      </div>
    </div>

    <div
      ref="bodyRef"
      class="panel-body file-body"
      :class="{ selecting }"
      @pointerdown="onBodyPointerDown"
    >
      <div
        v-if="marquee"
        class="selection-marquee"
        :style="{
          left: marquee.left + 'px',
          top: marquee.top + 'px',
          width: marquee.width + 'px',
          height: marquee.height + 'px',
        }"
      />

      <div v-if="!breadcrumb.length" class="empty-state">
        <strong>请选择左侧工作副本</strong>
        <div class="tiny">选择后可浏览文件、预览内容并执行 SVN 操作。</div>
      </div>

      <template v-else>
        <table v-if="viewMode === 'list'" class="file-list">
          <thead>
            <tr>
              <th style="width: 42%">名称</th>
              <th style="width: 12%">状态</th>
              <th style="width: 14%">大小</th>
              <th style="width: 32%">修改时间</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="entry in entries"
              :key="entry.path"
              :data-entry-path="entry.path"
              :class="{ selected: isSelected(entry.path) }"
              @click="onItemClick(entry, $event)"
              @dblclick="onDbl(entry)"
              @contextmenu.prevent.stop="onContext(entry, $event)"
            >
              <td>
                <div class="entry-name">
                  <FileIcon
                    :name="entry.name"
                    :is-dir="entry.isDir"
                    :svn-status="entry.svnStatus"
                    size="md"
                  />
                  <span class="entry-label" :title="entry.name">{{ entry.name }}</span>
                  <span
                    v-if="statusText(entry.svnStatus)"
                    class="status-chip"
                    :class="statusText(entry.svnStatus)!.className"
                    :title="statusText(entry.svnStatus)!.label"
                  >{{ statusText(entry.svnStatus)!.code }}</span>
                </div>
              </td>
              <td>
                <span
                  v-if="statusText(entry.svnStatus)"
                  class="status-badge"
                  :class="statusText(entry.svnStatus)!.className"
                  :title="statusText(entry.svnStatus)!.label"
                >
                  {{ statusText(entry.svnStatus)!.code }}
                </span>
                <span v-else class="muted tiny">—</span>
              </td>
              <td>{{ formatSize(entry.size, entry.isDir) }}</td>
              <td>{{ formatTime(entry.modified) }}</td>
            </tr>
          </tbody>
        </table>

        <div v-else-if="viewMode === 'icons'" class="icon-grid">
          <div
            v-for="entry in entries"
            :key="entry.path"
            class="icon-card"
            :data-entry-path="entry.path"
            :class="{ selected: isSelected(entry.path) }"
            @click="onItemClick(entry, $event)"
            @dblclick="onDbl(entry)"
            @contextmenu.prevent.stop="onContext(entry, $event)"
          >
            <div class="big-icon-wrap">
              <FileIcon
                :name="entry.name"
                :is-dir="entry.isDir"
                :svn-status="entry.svnStatus"
                size="lg"
              />
            </div>
            <div class="name" :title="entry.name">{{ entry.name }}</div>
            <div
              v-if="statusText(entry.svnStatus)"
              class="status-badge"
              :class="statusText(entry.svnStatus)!.className"
              :title="statusText(entry.svnStatus)!.label"
              style="margin-top: 6px"
            >
              {{ statusText(entry.svnStatus)!.code }}
            </div>
          </div>
        </div>

        <div v-else class="columns-view">
          <div
            v-for="(col, idx) in columnStacks"
            :key="col.path + idx"
            class="column"
            :style="{ width: columnWidth(col.path) + 'px', minWidth: columnWidth(col.path) + 'px' }"
          >
            <div class="column-scroll">
              <div
                v-for="entry in col.entries"
                :key="entry.path"
                class="column-item"
                :data-entry-path="entry.path"
                :class="{ selected: col.selected === entry.path || isSelected(entry.path) }"
                @click="onItemClick(entry, $event); entry.isDir && !($event.metaKey || $event.ctrlKey || $event.shiftKey) && emit('open', entry)"
                @dblclick="onDbl(entry)"
                @contextmenu.prevent.stop="onContext(entry, $event)"
              >
                <FileIcon
                  :name="entry.name"
                  :is-dir="entry.isDir"
                  :svn-status="entry.svnStatus"
                  size="sm"
                  :expanded="col.selected === entry.path && entry.isDir"
                />
                <span class="entry-label" :title="entry.name">{{ entry.name }}</span>
                <span
                  v-if="statusText(entry.svnStatus)"
                  class="status-chip"
                  :class="statusText(entry.svnStatus)!.className"
                  :title="statusText(entry.svnStatus)!.label"
                >{{ statusText(entry.svnStatus)!.code }}</span>
                <span v-if="entry.isDir" class="arrow">›</span>
              </div>
            </div>
            <div
              class="column-resizer"
              title="拖拽调整栏宽"
              @pointerdown="onColumnResizeStart(col.path, $event)"
            />
          </div>
        </div>
      </template>
    </div>
  </section>
</template>
