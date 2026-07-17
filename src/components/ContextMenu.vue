<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import type { ContextAction, FsEntry, Workspace, WorkspaceAction } from "../types";
import { canRevertSvnStatus, getSvnStatusMeta } from "../utils/materialIcon";

const props = defineProps<{
  visible: boolean;
  x: number;
  y: number;
  mode: "file" | "workspace";
  entry: FsEntry | null;
  workspace: Workspace | null;
  selectedCount?: number;
}>();

const emit = defineEmits<{
  close: [];
  reposition: [payload: { x: number; y: number }];
  fileAction: [action: ContextAction];
  workspaceAction: [action: WorkspaceAction];
}>();

const menuRef = ref<HTMLElement | null>(null);
let ignoreCloseUntil = 0;
let removeListeners: (() => void) | null = null;

function onKey(e: KeyboardEvent) {
  if (e.key === "Escape") {
    e.preventDefault();
    e.stopPropagation();
    emit("close");
  }
}

function shouldIgnoreClose() {
  return Date.now() < ignoreCloseUntil;
}

function isInsideMenu(target: EventTarget | null) {
  const el = target as HTMLElement | null;
  return !!el?.closest?.(".context-menu");
}

function onPointerDown(e: PointerEvent) {
  if (shouldIgnoreClose()) return;
  if (isInsideMenu(e.target)) return;
  emit("close");
}

function onMouseDown(e: MouseEvent) {
  if (shouldIgnoreClose()) return;
  if (isInsideMenu(e.target)) return;
  emit("close");
}

function onClick(e: MouseEvent) {
  if (shouldIgnoreClose()) return;
  if (isInsideMenu(e.target)) return;
  emit("close");
}

function onBrowserContext(e: MouseEvent) {
  // 右键点到菜单外：关闭；点到菜单内：阻止默认
  if (isInsideMenu(e.target)) {
    e.preventDefault();
    return;
  }
  if (shouldIgnoreClose()) return;
  emit("close");
}

function onScroll() {
  if (shouldIgnoreClose()) return;
  emit("close");
}

function onResize() {
  emit("close");
}

function clampMenuPosition(x: number, y: number, width: number, height: number) {
  const pad = 8;
  const vw = window.innerWidth;
  const vh = window.innerHeight;
  let nx = x;
  let ny = y;

  // 优先右下展开；放不下则向左/上翻转
  if (nx + width + pad > vw) nx = Math.max(pad, x - width);
  if (ny + height + pad > vh) ny = Math.max(pad, y - height);

  // 仍越界则硬夹紧
  nx = Math.min(Math.max(pad, nx), Math.max(pad, vw - width - pad));
  ny = Math.min(Math.max(pad, ny), Math.max(pad, vh - height - pad));
  return { x: Math.round(nx), y: Math.round(ny) };
}

async function adjustPositionToViewport() {
  await nextTick();
  const el = menuRef.value;
  if (!el || !props.visible) return;
  const rect = el.getBoundingClientRect();
  const next = clampMenuPosition(props.x, props.y, rect.width || 240, rect.height || 320);
  if (Math.abs(next.x - props.x) > 1 || Math.abs(next.y - props.y) > 1) {
    emit("reposition", next);
  }
}

function bindListeners() {
  unbindListeners();
  // 右键打开瞬间不要被同一次 pointer/context 事件立刻关掉
  ignoreCloseUntil = Date.now() + 320;
  window.addEventListener("keydown", onKey, true);
  window.addEventListener("pointerdown", onPointerDown, true);
  window.addEventListener("mousedown", onMouseDown, true);
  window.addEventListener("click", onClick, true);
  window.addEventListener("contextmenu", onBrowserContext, true);
  window.addEventListener("resize", onResize, true);
  // 捕获滚动：列表/面板滚动时关闭，避免悬浮错位
  window.addEventListener("scroll", onScroll, true);
  removeListeners = () => {
    window.removeEventListener("keydown", onKey, true);
    window.removeEventListener("pointerdown", onPointerDown, true);
    window.removeEventListener("mousedown", onMouseDown, true);
    window.removeEventListener("click", onClick, true);
    window.removeEventListener("contextmenu", onBrowserContext, true);
    window.removeEventListener("resize", onResize, true);
    window.removeEventListener("scroll", onScroll, true);
    removeListeners = null;
  };
}

function unbindListeners() {
  if (removeListeners) removeListeners();
}

watch(
  () => props.visible,
  async (v) => {
    if (v) {
      await nextTick();
      bindListeners();
      await adjustPositionToViewport();
      // 再测一次，处理字体/图标异步影响高度
      requestAnimationFrame(() => {
        void adjustPositionToViewport();
      });
    } else {
      unbindListeners();
    }
  },
);

watch(
  () => [props.x, props.y, props.mode, props.entry?.path, props.workspace?.id, props.selectedCount],
  async () => {
    if (props.visible) await adjustPositionToViewport();
  },
);

onBeforeUnmount(() => unbindListeners());

function actFile(action: ContextAction, e: MouseEvent) {
  e.preventDefault();
  e.stopPropagation();
  emit("fileAction", action);
}

function actWs(action: WorkspaceAction, e: MouseEvent) {
  e.preventDefault();
  e.stopPropagation();
  emit("workspaceAction", action);
}

const statusCode = computed(() => {
  const meta = getSvnStatusMeta(props.entry?.svnStatus);
  return meta?.code || null;
});

const multi = computed(() => (props.selectedCount || 1) > 1);

const canAdd = computed(() => multi.value || statusCode.value === "?" || statusCode.value === "I");
const canIgnore = computed(() => !multi.value && (statusCode.value === "?" || statusCode.value === "I" || !statusCode.value));
const canCommit = computed(
  () => multi.value || ["M", "A", "D", "R", "C", "?", "!", "~"].includes(statusCode.value || "") || !!props.entry?.isDir,
);
const canDiff = computed(
  () => !multi.value && (["M", "A", "D", "R", "C", "~"].includes(statusCode.value || "") || !!props.entry?.isDir),
);
// 未纳入版本控制(?)不可还原；多选时仍显示，执行时会过滤不可还原项
const canRevert = computed(() => {
  if (multi.value) return true;
  return canRevertSvnStatus(props.entry?.svnStatus);
});
const canResolved = computed(() => !multi.value && statusCode.value === "C");
const canBlame = computed(() => !multi.value && !props.entry?.isDir);
const canLock = computed(() => !multi.value ? !props.entry?.isDir : true);
const canUnlock = computed(() => canLock.value);
const canPatch = computed(() => !multi.value);
const canClean = computed(() => !multi.value && !!props.entry?.isDir);
const canRename = computed(() => !multi.value);
const canUpdate = computed(() => !multi.value);
const canLog = computed(() => !multi.value && !props.entry?.isDir);
const canInfo = computed(() => !multi.value);
const canProplist = computed(() => !multi.value);

const statusLabel = computed(() => {
  if (multi.value) return `已选 ${props.selectedCount} 项`;
  const meta = getSvnStatusMeta(props.entry?.svnStatus);
  if (!meta) return props.entry?.isDir ? "文件夹 · 正常" : "文件 · 正常";
  return `${props.entry?.isDir ? "文件夹" : "文件"} · ${meta.label}`;
});
</script>

<template>
  <div
    v-if="visible && ((mode === 'file' && entry) || (mode === 'workspace' && workspace))"
    ref="menuRef"
    class="context-menu"
    :style="{ left: `${x}px`, top: `${y}px` }"
    @click.stop
    @pointerdown.stop
    @mousedown.stop
    @contextmenu.prevent.stop
  >
    <template v-if="mode === 'file'">
      <div class="context-menu-caption">{{ statusLabel }}</div>

      <button v-if="canUpdate" type="button" @click="actFile('update', $event)">更新 <span class="kbd">⌘U</span></button>
      <button v-if="canCommit" type="button" @click="actFile('commit', $event)">提交... <span class="kbd">⌘↩</span></button>
      <button v-if="canAdd" type="button" @click="actFile('add', $event)">添加到版本控制</button>
      <button v-if="canIgnore" type="button" @click="actFile('ignore', $event)">添加到忽略列表</button>
      <button v-if="canDiff" type="button" @click="actFile('diff', $event)">查看差异 (DIFF)</button>
      <button v-if="canPatch" type="button" @click="actFile('patch', $event)">导出补丁 (Patch)</button>
      <button v-if="canBlame" type="button" @click="actFile('blame', $event)">注解 (Blame)</button>
      <button v-if="canLog" type="button" @click="actFile('log', $event)">查看历史</button>
      <button v-if="canInfo" type="button" @click="actFile('info', $event)">属性 / 信息</button>
      <button v-if="canProplist" type="button" @click="actFile('proplist', $event)">查看 SVN 属性</button>
      <button type="button" @click="actFile('reveal', $event)">在 Finder 中显示</button>

      <div class="divider" />

      <button v-if="canLock" type="button" @click="actFile('lock', $event)">锁定</button>
      <button v-if="canUnlock" type="button" @click="actFile('unlock', $event)">解锁</button>
      <button v-if="canClean" type="button" @click="actFile('clean', $event)">清理 (Clean)</button>
      <button v-if="canRename" type="button" @click="actFile('rename', $event)">重命名...</button>
      <button v-if="canResolved" type="button" @click="actFile('resolved', $event)">标记为已解决</button>
      <button v-if="canRevert" type="button" class="danger" @click="actFile('revert', $event)">还原</button>
      <button type="button" class="danger" @click="actFile('localDelete', $event)">本地删除</button>
      <button type="button" class="danger" @click="actFile('svnDelete', $event)">SVN 删除</button>
    </template>

    <template v-else>
      <div class="context-menu-caption">工作副本 · {{ workspace?.name }}</div>
      <button type="button" @click="actWs('update', $event)">更新 <span class="kbd">⌘U</span></button>
      <button type="button" @click="actWs('commit', $event)">提交... <span class="kbd">⌘↩</span></button>
      <button type="button" @click="actWs('diff', $event)">查看差异 (DIFF)</button>
      <button type="button" @click="actWs('patch', $event)">导出补丁 (Patch)</button>
      <button type="button" @click="actWs('log', $event)">查看历史</button>
      <button type="button" @click="actWs('info', $event)">属性 / 信息</button>
      <button type="button" @click="actWs('switch', $event)">切换地址 (Switch)...</button>
      <button type="button" @click="actWs('reveal', $event)">在 Finder 中显示</button>
      <div class="divider" />
      <button type="button" @click="actWs('clean', $event)">清理 (Clean)</button>
      <button type="button" @click="actWs('rename', $event)">重命名...</button>
      <button type="button" class="danger" @click="actWs('revert', $event)">还原全部本地修改</button>
      <button type="button" class="danger" @click="actWs('remove', $event)">从列表移除</button>
    </template>
  </div>
</template>
