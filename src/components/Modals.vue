<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { open } from "@tauri-apps/plugin-dialog";
import type { ProgressState, SvnLogEntry, SvnLogPath, SvnStatusItem } from "../types";
import { canRevertSvnStatus, getSvnStatusMeta } from "../utils/materialIcon";
import { isUnsupportedDiffPath } from "../utils/diffSupport";

const props = defineProps<{
  type: "checkout" | "commit" | "output" | "rename" | "switch" | "changes" | "history" | null;
  title?: string;
  output?: string;
  busy?: boolean;
  defaultPath?: string;
  renameFrom?: string;
  progress: ProgressState;
  commitRoot?: string;
  commitItems?: SvnStatusItem[];
  commitLoading?: boolean;
  switchRoot?: string;
  changesRoot?: string;
  changesItems?: SvnStatusItem[];
  changesLoading?: boolean;
  historyRoot?: string;
  historyItems?: SvnLogEntry[];
  historyLoading?: boolean;
  historySelectedRevision?: string;
}>();

const emit = defineEmits<{
  close: [];
  closeProgress: [];
  checkout: [payload: { url: string; path: string; name?: string }];
  commit: [payload: { message: string; paths: string[] }];
  commitAction: [payload: { action: "diff" | "diffAll"; path: string }];
  rename: [newName: string];
  switch: [payload: { url: string }];
  changesAction: [payload: { action: "diff" | "diffAll" | "revert" | "commit" | "reveal"; path: string }];
  refreshChanges: [];
  historySelect: [entry: SvnLogEntry];
  historyViewPath: [payload: { entry: SvnLogEntry; path: SvnLogPath }];
  historyViewRevision: [entry: SvnLogEntry];
  refreshHistory: [];
}>();

const url = ref("");
const path = ref("");
const name = ref("");
const message = ref("");
const newName = ref("");
const switchUrl = ref("");
const logBox = ref<HTMLElement | null>(null);
const checked = ref<Record<string, boolean>>({});
const historyLayoutRef = ref<HTMLElement | null>(null);
/** 上方提交列表占比（%），默认一半 */
const historyTopPct = ref(50);
const historySplitDragging = ref(false);

const HISTORY_SPLIT_MIN = 22;
const HISTORY_SPLIT_MAX = 78;
const HISTORY_SPLIT_PREF_KEY = "sf.history.splitTopPct";

function readHistorySplitPref() {
  try {
    const raw = localStorage.getItem(HISTORY_SPLIT_PREF_KEY);
    const n = Number.parseFloat(raw || "");
    if (Number.isFinite(n)) {
      return Math.min(HISTORY_SPLIT_MAX, Math.max(HISTORY_SPLIT_MIN, n));
    }
  } catch {
    // ignore
  }
  return 50;
}

historyTopPct.value = readHistorySplitPref();

function persistHistorySplitPref() {
  try {
    localStorage.setItem(HISTORY_SPLIT_PREF_KEY, String(Math.round(historyTopPct.value * 10) / 10));
  } catch {
    // ignore
  }
}

function onHistorySplitMove(ev: MouseEvent) {
  const el = historyLayoutRef.value;
  if (!el) return;
  const rect = el.getBoundingClientRect();
  if (rect.height <= 0) return;
  const y = ev.clientY - rect.top;
  const pct = (y / rect.height) * 100;
  historyTopPct.value = Math.min(HISTORY_SPLIT_MAX, Math.max(HISTORY_SPLIT_MIN, pct));
}

function onHistorySplitEnd() {
  if (!historySplitDragging.value) return;
  historySplitDragging.value = false;
  document.body.classList.remove("is-resizing-history-split");
  window.removeEventListener("mousemove", onHistorySplitMove);
  window.removeEventListener("mouseup", onHistorySplitEnd);
  persistHistorySplitPref();
}

function onHistorySplitStart(e: MouseEvent) {
  if (e.button !== 0) return;
  e.preventDefault();
  e.stopPropagation();
  historySplitDragging.value = true;
  document.body.classList.add("is-resizing-history-split");
  window.addEventListener("mousemove", onHistorySplitMove);
  window.addEventListener("mouseup", onHistorySplitEnd);
  onHistorySplitMove(e);
}

onBeforeUnmount(() => {
  onHistorySplitEnd();
});

function historySummary(entry: SvnLogEntry) {
  return entry.message.split("\n").find((line) => line.trim()) || "(无说明)";
}

function historyDateLabel(entry: SvnLogEntry) {
  if (!entry.date) return "—";
  const date = new Date(entry.date);
  return Number.isNaN(date.getTime()) ? entry.date : date.toLocaleString();
}

function historyPathLabel(entry: SvnLogEntry) {
  return entry.paths.length ? `${entry.paths.length} 个变更路径` : "无路径";
}

const selectedHistoryEntry = computed(() => {
  const items = props.historyItems || [];
  if (!items.length) return null;
  return items.find((e) => e.revision === props.historySelectedRevision) || items[0] || null;
});

function pathBaseName(repoPath: string) {
  const clean = (repoPath || "").replace(/\\/g, "/");
  const parts = clean.split("/").filter(Boolean);
  return parts[parts.length - 1] || repoPath || "—";
}

function pathActionMeta(action?: string | null) {
  return getSvnStatusMeta(action) || { code: action || "?", label: action || "变更", className: "other" };
}

async function pickCheckoutDirectory() {
  if (props.busy) return;
  const selected = await open({
    directory: true,
    multiple: false,
    title: "选择检出目标文件夹",
    defaultPath: path.value.trim() || props.defaultPath || undefined,
  });
  if (!selected || Array.isArray(selected)) return;
  path.value = selected;
}

function statusMeta(code: string) {
  return getSvnStatusMeta(code);
}

/** 判断某项是否可以做文本 diff（非目录、非二进制、扩展名支持） */
function canDiffItem(item: { path: string; isDir?: boolean; binary?: boolean; status?: string }) {
  // 新增（A）状态没有旧文本，diff 意义不大但仍可展示为新增文件
  if (item.status === "D") return true;
  if (item.status === "A") return true;
  return !isUnsupportedDiffPath(item.path, { isDir: item.isDir, binary: item.binary });
}

function resetChecked(items: SvnStatusItem[] = []) {
  const next: Record<string, boolean> = {};
  for (const item of items) {
    // 默认勾选可提交变更；忽略项默认不勾选
    next[item.path] = item.status !== "I";
  }
  checked.value = next;
}

const selectedPaths = computed(() =>
  (props.commitItems || []).filter((i) => checked.value[i.path]).map((i) => i.path),
);

const selectedCount = computed(() => selectedPaths.value.length);
const allChecked = computed(() => {
  const items = props.commitItems || [];
  return items.length > 0 && items.every((i) => checked.value[i.path]);
});

function toggleAll(v: boolean) {
  const next: Record<string, boolean> = { ...checked.value };
  for (const item of props.commitItems || []) next[item.path] = v;
  checked.value = next;
}

function toggleOne(pathValue: string, v: boolean) {
  checked.value = { ...checked.value, [pathValue]: v };
}

// ── 树形分组 ──────────────────────────────────────────────

/** 获取文件所属的文件夹路径（相对于 commitRoot/changesRoot），末尾带 "/" */
function dirOf(item: SvnStatusItem): string {
  const rel = (item.relativePath || item.name || "").replace(/\\/g, "/");
  const slash = rel.lastIndexOf("/");
  return slash < 0 ? "" : rel.substring(0, slash + 1);
}

/** 提交弹窗：按文件夹分组的树形结构 */
const commitTree = computed(() => {
  const items = props.commitItems || [];
  const groups: { dir: string; items: SvnStatusItem[] }[] = [];
  const map = new Map<string, SvnStatusItem[]>();
  for (const item of items) {
    const dir = dirOf(item);
    if (!map.has(dir)) {
      map.set(dir, []);
      groups.push({ dir, items: [] });
    }
    map.get(dir)!.push(item);
  }
  // 填充 items 引用
  for (const g of groups) g.items = map.get(g.dir)!;
  // 根文件夹（""）排在最前，其余按字母排序
  groups.sort((a, b) => {
    if (!a.dir) return -1;
    if (!b.dir) return 1;
    return a.dir < b.dir ? -1 : 1;
  });
  return groups;
});

/** 变更弹窗：按文件夹分组的树形结构 */
const changesTree = computed(() => {
  const items = props.changesItems || [];
  const groups: { dir: string; items: SvnStatusItem[] }[] = [];
  const map = new Map<string, SvnStatusItem[]>();
  for (const item of items) {
    const dir = dirOf(item);
    if (!map.has(dir)) {
      map.set(dir, []);
      groups.push({ dir, items: [] });
    }
    map.get(dir)!.push(item);
  }
  for (const g of groups) g.items = map.get(g.dir)!;
  groups.sort((a, b) => {
    if (!a.dir) return -1;
    if (!b.dir) return 1;
    return a.dir < b.dir ? -1 : 1;
  });
  return groups;
});

/** 某文件夹分组下所有文件的勾选状态：all | none | some */
function groupCheckState(groupItems: SvnStatusItem[]): "all" | "none" | "some" {
  let checkedCount = 0;
  for (const item of groupItems) {
    if (checked.value[item.path]) checkedCount++;
  }
  if (checkedCount === 0) return "none";
  if (checkedCount === groupItems.length) return "all";
  return "some";
}

/** 勾选/取消勾选某文件夹分组下的所有文件 */
function toggleGroup(groupItems: SvnStatusItem[], v: boolean) {
  const next = { ...checked.value };
  for (const item of groupItems) next[item.path] = v;
  checked.value = next;
}

/** 缩进层级：根据目录深度计算 padding-left */
function groupIndent(dir: string): number {
  if (!dir) return 0;
  return dir.split("/").filter(Boolean).length;
}

// ── 文件夹展开/合拢 ──────────────────────────────────────────

/** 合拢的文件夹路径集合（默认全部展开，仅记录被合拢的） */
const collapsed = ref<Record<string, boolean>>({});

/** 切换某文件夹的展开/合拢状态 */
function toggleCollapse(dir: string) {
  collapsed.value = { ...collapsed.value, [dir]: !collapsed.value[dir] };
}

/** 某文件夹是否已合拢 */
function isCollapsed(dir: string): boolean {
  return !!collapsed.value[dir];
}

/** 某祖先路径是否已合拢（不含自身） */
function hasCollapsedAncestor(dir: string): boolean {
  if (!dir) return false;
  const parts = dir.split("/").filter(Boolean);
  for (let i = 0; i < parts.length - 1; i++) {
    const parentDir = parts.slice(0, i + 1).join("/") + "/";
    if (collapsed.value[parentDir]) return true;
  }
  return false;
}

/** 文件夹标题行是否显示（祖先未合拢） */
function isGroupVisible(dir: string): boolean {
  return !hasCollapsedAncestor(dir);
}

/** 判断某文件是否应该显示（其所属文件夹未合拢） */
function isFileVisible(item: SvnStatusItem): boolean {
  const dir = dirOf(item);
  if (!dir) return true; // 根目录文件始终显示
  if (collapsed.value[dir] || hasCollapsedAncestor(dir)) return false;
  return true;
}

/** 提交弹窗文件可见性 Map（响应式） */
const commitFileVisible = computed<Record<string, boolean>>(() => {
  const map: Record<string, boolean> = {};
  for (const grp of commitTree.value) {
    for (const item of grp.items) {
      map[item.path] = isFileVisible(item);
    }
  }
  return map;
});

/** 变更弹窗文件可见性 Map（响应式） */
const changesFileVisible = computed<Record<string, boolean>>(() => {
  const map: Record<string, boolean> = {};
  for (const grp of changesTree.value) {
    for (const item of grp.items) {
      map[item.path] = isFileVisible(item);
    }
  }
  return map;
});

/** 全部展开 */
function expandAll() {
  collapsed.value = {};
}

/** 全部合拢 */
function collapseAll() {
  const next: Record<string, boolean> = {};
  for (const grp of commitTree.value) {
    if (grp.dir) next[grp.dir] = true;
  }
  collapsed.value = next;
}

watch(
  () => props.type,
  (t) => {
    if (t === "checkout") {
      url.value = "";
      path.value = props.defaultPath || "";
      name.value = "";
    }
    if (t === "commit") {
      message.value = "";
      resetChecked(props.commitItems || []);
      collapsed.value = {};
    }
    if (t === "rename") {
      newName.value = props.renameFrom || "";
    }
    if (t === "switch") {
      switchUrl.value = "";
    }
  },
);

watch(
  () => props.commitItems,
  (items) => {
    if (props.type === "commit") resetChecked(items || []);
  },
  { deep: true },
);

watch(
  () => props.progress.lines.length,
  async () => {
    await nextTick();
    if (logBox.value) {
      logBox.value.scrollTop = logBox.value.scrollHeight;
    }
  },
);

function submitCheckout() {
  if (!url.value.trim() || !path.value.trim()) return;
  emit("checkout", {
    url: url.value.trim(),
    path: path.value.trim(),
    name: name.value.trim() || undefined,
  });
}

function submitCommit() {
  if (!message.value.trim() || !selectedPaths.value.length) return;
  emit("commit", {
    message: message.value.trim(),
    paths: [...selectedPaths.value],
  });
}

function submitRename() {
  if (!newName.value.trim()) return;
  emit("rename", newName.value.trim());
}

function submitSwitch() {
  if (!switchUrl.value.trim()) return;
  emit("switch", { url: switchUrl.value.trim() });
}

</script>

<template>
  <div v-if="type" class="modal-mask" @click.self="!busy && emit('close')">
    <div v-if="type === 'checkout'" class="modal">
      <div class="modal-header">
        <h3>检出工作副本</h3>
        <button class="btn btn-ghost btn-icon" :disabled="busy" @click="emit('close')">✕</button>
      </div>
      <div class="modal-body">
        <div class="field">
          <label>SVN 地址</label>
          <input v-model="url" placeholder="svn://svn.example.com/repo/trunk" :disabled="busy" />
        </div>
        <div class="field">
          <label>本地目录</label>
          <div class="path-picker">
            <input
              v-model="path"
              placeholder="/Users/you/Projects/my-repo"
              :disabled="busy"
              spellcheck="false"
            />
            <button
              type="button"
              class="btn"
              :disabled="busy"
              title="选择文件夹"
              @click="pickCheckoutDirectory"
            >
              选择目录
            </button>
          </div>
        </div>
        <div class="field">
          <label>显示名称（可选）</label>
          <input v-model="name" placeholder="默认取文件夹名" :disabled="busy" />
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn" :disabled="busy" @click="emit('close')">取消</button>
        <button
          class="btn btn-primary"
          :disabled="busy || !url.trim() || !path.trim()"
          @click="submitCheckout"
        >
          {{ busy ? "检出中..." : "开始检出" }}
        </button>
      </div>
    </div>

    <div v-else-if="type === 'commit'" class="modal commit-modal">
      <div class="modal-header">
        <h3>提交更改</h3>
        <button class="btn btn-ghost btn-icon" :disabled="busy" @click="emit('close')">✕</button>
      </div>
      <div class="modal-body">
        <div class="field">
          <label>目标</label>
          <div class="tiny mono muted" :title="commitRoot">{{ commitRoot || "—" }}</div>
        </div>

        <div class="field commit-list-field">
          <div class="commit-list-head">
            <label>变更文件</label>
            <div class="commit-list-actions">
              <button type="button" class="btn btn-ghost tiny-btn" :disabled="busy || commitLoading" @click="expandAll">展开</button>
              <button type="button" class="btn btn-ghost tiny-btn" :disabled="busy || commitLoading" @click="collapseAll">合拢</button>
              <button type="button" class="btn btn-ghost tiny-btn" :disabled="busy || commitLoading" @click="toggleAll(true)">全选</button>
              <button type="button" class="btn btn-ghost tiny-btn" :disabled="busy || commitLoading" @click="toggleAll(false)">全不选</button>
              <span class="tiny muted">已选 {{ selectedCount }} / {{ (commitItems || []).length }}</span>
            </div>
          </div>

          <div v-if="commitLoading" class="commit-empty">正在读取变更列表...</div>
          <div v-else-if="!(commitItems || []).length" class="commit-empty">当前没有可提交的变更。</div>
          <div v-else class="commit-file-list">
            <label class="commit-file-row all">
              <input type="checkbox" :checked="allChecked" :disabled="busy" @change="toggleAll(($event.target as HTMLInputElement).checked)" />
              <span>全部变更</span>
            </label>
            <template v-for="grp in commitTree" :key="grp.dir || '__root__'">
              <!-- 文件夹分组标题行（有目录时才显示） -->
              <div
                v-if="grp.dir"
                class="commit-file-row tree-folder"
                :class="{ 'tree-row-hidden': !isGroupVisible(grp.dir) }"
                :style="{ paddingLeft: 10 + groupIndent(grp.dir) * 16 + 'px' }"
                @click="toggleCollapse(grp.dir)"
              >
                <span
                  class="tree-toggle"
                  :title="isCollapsed(grp.dir) ? '展开' : '合拢'"
                >{{ isCollapsed(grp.dir) ? '▶' : '▼' }}</span>
                <input
                  type="checkbox"
                  :checked="groupCheckState(grp.items) === 'all'"
                  :indeterminate.prop="groupCheckState(grp.items) === 'some'"
                  :disabled="busy"
                  @click.stop
                  @change="toggleGroup(grp.items, ($event.target as HTMLInputElement).checked)"
                />
                <span class="tree-folder-icon">{{ isCollapsed(grp.dir) ? '📂' : '📁' }}</span>
                <span class="tree-folder-name">{{ grp.dir }}</span>
                <span class="tiny muted">{{ grp.items.length }} 个</span>
              </div>
              <!-- 该文件夹下的文件 -->
              <div
                v-for="item in grp.items"
                :key="item.path"
                class="commit-file-row tree-file commit-tree-file"
                :class="{ 'tree-row-hidden': commitFileVisible[item.path] === false }"
                :style="{ paddingLeft: 10 + (grp.dir ? (groupIndent(grp.dir) + 1) : 0) * 16 + 'px' }"
                :title="item.path"
              >
                <span class="tree-toggle-spacer"></span>
                <input
                  type="checkbox"
                  class="tree-file-checkbox"
                  :checked="!!checked[item.path]"
                  :disabled="busy"
                  @change="toggleOne(item.path, ($event.target as HTMLInputElement).checked)"
                />
                <span
                  v-if="statusMeta(item.status)"
                  class="status-badge"
                  :class="statusMeta(item.status)!.className"
                  :title="statusMeta(item.status)!.label"
                >{{ statusMeta(item.status)!.code }}</span>
                <span v-else class="status-badge other">?</span>
                <span class="commit-file-name">{{ item.name }}</span>
                <div class="changes-actions">
                  <button
                    v-if="canDiffItem(item)"
                    type="button"
                    class="btn btn-ghost tiny-btn"
                    :disabled="busy"
                    @click.stop="emit('commitAction', { action: 'diff', path: item.path })"
                  >DIFF</button>
                </div>
              </div>
            </template>
          </div>
        </div>

        <div class="field">
          <label>提交说明</label>
          <textarea
            v-model="message"
            placeholder="请输入提交信息..."
            :disabled="busy"
            rows="4"
          />
        </div>
        <div class="tiny muted">
          将仅提交勾选的文件；未纳入版本控制的项会在提交前自动 `svn add`，磁盘缺失（`!`）的项会自动 `svn delete`。
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn" :disabled="busy" @click="emit('close')">取消</button>
        <button
          class="btn"
          :disabled="busy || commitLoading || !(commitItems || []).length"
          @click="emit('commitAction', { action: 'diffAll', path: commitRoot || '' })"
        >查看所有 diff</button>
        <button
          class="btn btn-primary"
          :disabled="busy || commitLoading || !message.trim() || !selectedCount"
          @click="submitCommit"
        >
          {{ busy ? "提交中..." : `提交 (${selectedCount})` }}
        </button>
      </div>
    </div>

    <div v-else-if="type === 'rename'" class="modal">
      <div class="modal-header">
        <h3>重命名</h3>
        <button class="btn btn-ghost btn-icon" :disabled="busy" @click="emit('close')">✕</button>
      </div>
      <div class="modal-body">
        <div class="field">
          <label>当前名称</label>
          <input :value="renameFrom || ''" disabled />
        </div>
        <div class="field">
          <label>新名称</label>
          <input v-model="newName" placeholder="输入新文件/文件夹名" :disabled="busy" @keyup.enter="submitRename" />
        </div>
        <div class="tiny muted">优先执行 `svn move`；未纳入版本控制时回退本地重命名。</div>
      </div>
      <div class="modal-footer">
        <button class="btn" :disabled="busy" @click="emit('close')">取消</button>
        <button
          class="btn btn-primary"
          :disabled="busy || !newName.trim() || newName.trim() === (renameFrom || '')"
          @click="submitRename"
        >
          {{ busy ? "重命名中..." : "确定" }}
        </button>
      </div>
    </div>

    <div v-else-if="type === 'output'" class="modal wide">
      <div class="modal-header">
        <h3>{{ title || "输出" }}</h3>
        <button class="btn btn-ghost btn-icon" @click="emit('close')">✕</button>
      </div>
      <div class="modal-body">
        <div class="output-box">{{ output || "(无输出)" }}</div>
      </div>
      <div class="modal-footer">
        <button class="btn btn-primary" @click="emit('close')">关闭</button>
      </div>
    </div>

    <div v-else-if="type === 'switch'" class="modal">
      <div class="modal-header">
        <h3>切换工作副本地址 (Switch)</h3>
        <button class="btn btn-ghost btn-icon" :disabled="busy" @click="emit('close')">✕</button>
      </div>
      <div class="modal-body">
        <div class="field">
          <label>当前工作副本</label>
          <div class="tiny mono muted" :title="switchRoot">{{ switchRoot || "—" }}</div>
        </div>
        <div class="field">
          <label>目标 SVN 地址</label>
          <input
            v-model="switchUrl"
            placeholder="svn://server/repo/branches/feature-x"
            :disabled="busy"
            spellcheck="false"
            @keyup.enter="submitSwitch"
          />
        </div>
        <div class="tiny muted">相当于执行 svn switch &lt;url&gt;，用于切换分支/标签/路径。</div>
      </div>
      <div class="modal-footer">
        <button class="btn" :disabled="busy" @click="emit('close')">取消</button>
        <button class="btn btn-primary" :disabled="busy || !switchUrl.trim()" @click="submitSwitch">
          {{ busy ? "切换中..." : "开始切换" }}
        </button>
      </div>
    </div>

    <div v-else-if="type === 'changes'" class="modal commit-modal">
      <div class="modal-header">
        <h3>本地变更</h3>
        <button class="btn btn-ghost btn-icon" :disabled="busy" @click="emit('close')">✕</button>
      </div>
      <div class="modal-body">
        <div class="field">
          <label>范围</label>
          <div class="tiny mono muted" :title="changesRoot">{{ changesRoot || "—" }}</div>
        </div>
        <div class="field commit-list-field">
          <div class="commit-list-head">
            <label>变更列表</label>
            <div class="commit-list-actions">
              <button type="button" class="btn btn-ghost tiny-btn" :disabled="busy || changesLoading" @click="emit('refreshChanges')">刷新</button>
              <span class="tiny muted">{{ (changesItems || []).length }} 项</span>
            </div>
          </div>
          <div v-if="changesLoading" class="commit-empty">正在读取变更...</div>
          <div v-else-if="!(changesItems || []).length" class="commit-empty">当前没有本地变更。</div>
          <div v-else class="commit-file-list">
            <template v-for="grp in changesTree" :key="grp.dir || '__root__'">
              <!-- 文件夹分组标题行 -->
              <div
                v-if="grp.dir"
                class="commit-file-row tree-folder changes-tree-folder"
                :class="{ 'tree-row-hidden': !isGroupVisible(grp.dir) }"
                :style="{ paddingLeft: 10 + groupIndent(grp.dir) * 16 + 'px' }"
                @click="toggleCollapse(grp.dir)"
              >
                <span
                  class="tree-toggle"
                  :title="isCollapsed(grp.dir) ? '展开' : '合拢'"
                >{{ isCollapsed(grp.dir) ? '▶' : '▼' }}</span>
                <span class="tree-folder-icon">{{ isCollapsed(grp.dir) ? '📂' : '📁' }}</span>
                <span class="tree-folder-name">{{ grp.dir }}</span>
                <span class="tiny muted">{{ grp.items.length }} 个</span>
              </div>
              <!-- 该文件夹下的文件 -->
              <div
                v-for="item in grp.items"
                :key="item.path"
                class="commit-file-row tree-file changes-tree-file"
                :class="{ 'tree-row-hidden': changesFileVisible[item.path] === false }"
                :style="{ paddingLeft: 10 + (grp.dir ? (groupIndent(grp.dir) + 1) : 0) * 16 + 'px' }"
                :title="item.path"
              >
                <span class="tree-toggle-spacer"></span>
                <span
                  v-if="statusMeta(item.status)"
                  class="status-badge"
                  :class="statusMeta(item.status)!.className"
                  :title="statusMeta(item.status)!.label"
                >{{ statusMeta(item.status)!.code }}</span>
                <span v-else class="status-badge other">?</span>
                <span class="commit-file-name">{{ item.name }}</span>
                <div class="changes-actions">
                  <button type="button" class="btn btn-ghost tiny-btn" :disabled="busy" @click="emit('changesAction', { action: 'diff', path: item.path })">DIFF</button>
                  <button type="button" class="btn btn-ghost tiny-btn" :disabled="busy" @click="emit('changesAction', { action: 'reveal', path: item.path })">定位</button>
                  <button
                    v-if="canRevertSvnStatus(item.status)"
                    type="button"
                    class="btn btn-ghost tiny-btn danger-text"
                    :disabled="busy"
                    @click="emit('changesAction', { action: 'revert', path: item.path })"
                  >还原</button>
                </div>
              </div>
            </template>
          </div>
        </div>
        <div class="tiny muted">可在此快速浏览本地修改；需要提交时请使用「提交」并勾选文件。</div>
      </div>
      <div class="modal-footer">
        <button class="btn" :disabled="busy" @click="emit('close')">关闭</button>
        <button class="btn" :disabled="busy || !(changesItems || []).length" @click="emit('changesAction', { action: 'diffAll', path: changesRoot || '' })">查看所有 diff</button>
        <button class="btn btn-primary" :disabled="busy || !(changesItems || []).length" @click="emit('changesAction', { action: 'commit', path: changesRoot || '' })">去提交...</button>
      </div>
    </div>

    <div v-else-if="type === 'history'" class="modal commit-modal history-modal">
      <div class="modal-header">
        <h3>提交历史</h3>
        <button class="btn btn-ghost btn-icon" :disabled="busy" @click="emit('close')">✕</button>
      </div>
      <div class="modal-body history-body">
        <div class="field history-path-field">
          <label>路径</label>
          <div class="tiny mono muted" :title="historyRoot">{{ historyRoot || "—" }}</div>
        </div>

        <div v-if="historyLoading" class="commit-empty">正在读取历史...</div>
        <div v-else-if="!(historyItems || []).length" class="commit-empty">当前没有历史记录。</div>
        <div
          v-else
          ref="historyLayoutRef"
          class="history-layout"
          :class="{ splitting: historySplitDragging }"
          :style="{ '--history-top-pct': historyTopPct + '%' }"
        >
          <div class="history-top">
            <div class="commit-list-head">
              <label>提交列表</label>
              <div class="commit-list-actions">
                <button type="button" class="btn btn-ghost tiny-btn" :disabled="busy || historyLoading" @click="emit('refreshHistory')">刷新</button>
                <span class="tiny muted">{{ (historyItems || []).length }} 条</span>
              </div>
            </div>
            <div class="commit-file-list history-list">
              <button
                v-for="entry in historyItems"
                :key="entry.revision"
                type="button"
                class="commit-file-row history-row"
                :class="{ active: entry.revision === (selectedHistoryEntry?.revision || historySelectedRevision) }"
                :title="historySummary(entry)"
                @click="emit('historySelect', entry)"
              >
                <span class="status-badge history-rev">r{{ entry.revision }}</span>
                <div class="history-row-main">
                  <span class="commit-file-name history-message">{{ historySummary(entry) }}</span>
                  <span class="tiny muted history-meta">
                    {{ entry.author || "—" }} · {{ historyDateLabel(entry) }} · {{ historyPathLabel(entry) }}
                  </span>
                </div>
              </button>
            </div>
          </div>

          <div
            class="history-splitter"
            title="拖拽调整上下占比"
            @mousedown="onHistorySplitStart"
          >
            <span class="history-splitter-grip" />
          </div>

          <div class="history-bottom" v-if="selectedHistoryEntry">
            <div class="history-detail-head">
              <div class="history-detail-rev">修订 r{{ selectedHistoryEntry.revision }}</div>
              <div class="history-detail-meta">
                <span>作者：{{ selectedHistoryEntry.author || "—" }}</span>
                <span>时间：{{ historyDateLabel(selectedHistoryEntry) }}</span>
                <span>文件：{{ selectedHistoryEntry.paths.length }} 个</span>
              </div>
            </div>

            <div class="field history-msg-field">
              <label>提交说明</label>
              <pre class="history-message-box">{{ selectedHistoryEntry.message?.trim() || "(无说明)" }}</pre>
            </div>

            <div class="field history-files-field">
              <div class="commit-list-head">
                <label>本次提交文件</label>
                <span class="tiny muted">点击文件可查看该版本差异</span>
              </div>
              <div v-if="!selectedHistoryEntry.paths.length" class="commit-empty compact">该次提交没有路径信息（可能未使用 -v 日志）。</div>
              <div v-else class="commit-file-list history-path-list">
                <button
                  v-for="(item, idx) in selectedHistoryEntry.paths"
                  :key="`${selectedHistoryEntry.revision}-${idx}-${item.path}`"
                  type="button"
                  class="commit-file-row history-path-row"
                  :title="item.path"
                  @click="emit('historyViewPath', { entry: selectedHistoryEntry, path: item })"
                >
                  <span class="status-badge" :class="pathActionMeta(item.action).className">{{ pathActionMeta(item.action).code }}</span>
                  <span class="commit-file-name history-path-name">{{ pathBaseName(item.path) }}</span>
                  <span class="tiny muted history-path-full mono">{{ item.path }}</span>
                  <span v-if="item.kind" class="tiny muted">{{ item.kind }}</span>
                </button>
              </div>
            </div>
          </div>
          <div v-else class="history-bottom history-bottom-empty">
            <div class="commit-empty">请选择上方某次提交查看详情。</div>
          </div>
        </div>
      </div>
      <div class="modal-footer history-footer">
        <div class="tiny muted history-footer-tip">选择提交可查看说明、时间与变更文件列表。</div>
        <div class="history-footer-actions">
          <button class="btn" :disabled="busy" @click="emit('close')">关闭</button>
          <button
            class="btn btn-primary"
            :disabled="busy || !selectedHistoryEntry"
            @click="selectedHistoryEntry && emit('historyViewRevision', selectedHistoryEntry)"
          >
            查看此版本差异
          </button>
        </div>
      </div>
    </div>
  </div>

  <div v-if="progress.visible" class="modal-mask progress-mask">
    <div class="modal wide progress-modal">
      <div class="modal-header">
        <div>
          <h3>{{ progress.title }}</h3>
          <div class="tiny muted" style="margin-top: 4px">{{ progress.status }}</div>
        </div>
        <button
          class="btn btn-ghost btn-icon"
          :disabled="progress.running"
          :title="progress.running ? '进行中，请稍候' : '关闭'"
          @click="emit('closeProgress')"
        >
          ✕
        </button>
      </div>

      <div class="modal-body">
        <div class="progress-meta">
          <div
            class="progress-indicator"
            :class="{ running: progress.running, ok: progress.success === true, bad: progress.success === false }"
          >
            <span v-if="progress.running" class="spinner small" />
            <span v-else-if="progress.success === true">✓</span>
            <span v-else-if="progress.success === false">✕</span>
            <span v-else>•</span>
            <span>
              {{
                progress.running
                  ? "进行中"
                  : progress.success
                    ? "已完成"
                    : progress.success === false
                      ? "失败"
                      : "待命"
              }}
            </span>
          </div>
          <div class="tiny muted">实时日志（stdout / stderr）</div>
        </div>

        <div class="progress-track" v-if="progress.running">
          <div class="progress-bar indeterminate" />
        </div>
        <div class="progress-track done" v-else-if="progress.success === true">
          <div class="progress-bar full ok" />
        </div>
        <div class="progress-track done" v-else-if="progress.success === false">
          <div class="progress-bar full bad" />
        </div>

        <div ref="logBox" class="output-box live-log">
          <div v-if="!progress.lines.length" class="muted">(等待输出...)</div>
          <div
            v-for="(line, idx) in progress.lines"
            :key="idx"
            class="log-line"
            :class="{ err: line.startsWith('[stderr] ') }"
          >
            {{ line }}
          </div>
        </div>
      </div>

      <div class="modal-footer">
        <button class="btn btn-primary" :disabled="progress.running" @click="emit('closeProgress')">
          {{ progress.running ? "处理中..." : "关闭" }}
        </button>
      </div>
    </div>
  </div>
</template>
