<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { confirm as nativeConfirm } from "@tauri-apps/plugin-dialog";
import * as api from "../api/svn";
import type { ConflictAccept, ConflictDetail, ConflictItem, ConflictSide } from "../types";
import { buildLineDiff, type SideBySideRow } from "../utils/diffEngine";

const props = defineProps<{
  open: boolean;
  root: string;
  focus?: string;
}>();

const emit = defineEmits<{
  close: [];
  changed: [];
}>();

const conflicts = ref<ConflictItem[]>([]);
const detail = ref<ConflictDetail | null>(null);
const selectedPath = ref("");
const listLoading = ref(false);
const detailLoading = ref(false);
const resolving = ref(false);
const listError = ref("");
const detailError = ref("");
const actionError = ref("");
const compareMode = ref<"mine-theirs" | "base-mine" | "working">("mine-theirs");
let detailToken = 0;

const MAX_DIFF_ROWS = 1800;
const MAX_TEXT_CHARS = 300_000;

const stillConflict = computed(
  () => !!detail.value && (detail.value.text || detail.value.property || detail.value.tree),
);
const textConflict = computed(() => !!detail.value?.text && !detail.value?.isDir);
const canUseBase = computed(() => textConflict.value || !!detail.value?.base.available);

const pair = computed(() => {
  if (!detail.value || compareMode.value === "working") return null;
  if (compareMode.value === "base-mine") {
    return {
      leftTitle: "基准版本",
      rightTitle: "我的版本",
      left: detail.value.base,
      right: detail.value.mine,
    };
  }
  return {
    leftTitle: "我的版本",
    rightTitle: "对方版本",
    left: detail.value.mine,
    right: detail.value.theirs,
  };
});

const previewTooBig = computed(() => {
  const current = pair.value;
  if (!current) return false;
  return current.left.text.length > MAX_TEXT_CHARS || current.right.text.length > MAX_TEXT_CHARS;
});

const diffView = computed(() => {
  const current = pair.value;
  if (!current || previewTooBig.value || !current.left.available || !current.right.available) {
    return null;
  }
  const built = buildLineDiff(current.left.text, current.right.text);
  return {
    rows: built.sideBySide.slice(0, MAX_DIFF_ROWS),
    truncated: built.sideBySide.length > MAX_DIFF_ROWS,
    additions: built.stats.additions,
    deletions: built.stats.deletions,
  };
});

const workingLines = computed(() => {
  const text = detail.value?.working.text || "";
  if (!text) return [];
  const parts = text.split("\n");
  if (parts.length && parts[parts.length - 1] === "") parts.pop();
  return parts.slice(0, MAX_DIFF_ROWS);
});

const workingTruncated = computed(() => {
  const text = detail.value?.working.text || "";
  if (!text) return false;
  const count = text.endsWith("\n") ? text.split("\n").length - 1 : text.split("\n").length;
  return count > MAX_DIFF_ROWS;
});

watch(
  () => [props.open, props.root, props.focus] as const,
  async ([open]) => {
    if (!open) return;
    compareMode.value = "mine-theirs";
    actionError.value = "";
    await loadList(props.focus || "");
  },
);

async function loadList(prefer = "") {
  if (!props.root) {
    conflicts.value = [];
    detail.value = null;
    listError.value = "没有可检查的路径";
    return;
  }
  listLoading.value = true;
  listError.value = "";
  try {
    const items = await api.svnListConflicts(props.root);
    if (!props.open) return;
    conflicts.value = items;
    const wanted = prefer || selectedPath.value;
    const hit = items.find((item) => item.path === wanted) || items[0];
    if (hit) {
      await selectItem(hit.path);
    } else {
      selectedPath.value = "";
      detail.value = null;
    }
  } catch (e) {
    conflicts.value = [];
    detail.value = null;
    selectedPath.value = "";
    listError.value = e instanceof Error ? e.message : String(e);
  } finally {
    listLoading.value = false;
  }
}

async function selectItem(path: string) {
  const token = ++detailToken;
  selectedPath.value = path;
  detailLoading.value = true;
  detailError.value = "";
  actionError.value = "";
  try {
    const next = await api.svnConflictDetail(path);
    if (token !== detailToken || !props.open) return;
    detail.value = next;
    if (!next.mine.available && !next.theirs.available && next.working.available) {
      compareMode.value = "working";
    } else if (compareMode.value === "working" && next.mine.available && next.theirs.available) {
      compareMode.value = "mine-theirs";
    }
  } catch (e) {
    if (token !== detailToken) return;
    detail.value = null;
    detailError.value = e instanceof Error ? e.message : String(e);
  } finally {
    if (token === detailToken) detailLoading.value = false;
  }
}

function markerKind(line: string) {
  if (line.startsWith("<<<<<<<")) return "start";
  if (line.startsWith("|||||||") || line.startsWith("=======")) return "mid";
  if (line.startsWith(">>>>>>>")) return "end";
  return "";
}

function sideText(side: ConflictSide | undefined) {
  if (!side) return "";
  if (side.available) return side.text;
  return side.message || "这一侧没有可显示的内容";
}

async function confirmAccept(accept: ConflictAccept, name: string) {
  const copy: Record<ConflictAccept, { title: string; ok: string; message: string }> = {
    "mine-full": {
      title: "采用我的版本",
      ok: "采用我的",
      message: `用更新前的本地版本解决「${name}」？\n对方这次的改动会被丢弃。`,
    },
    "theirs-full": {
      title: "采用对方版本",
      ok: "采用对方",
      message: `用仓库里的版本解决「${name}」？\n你本地还没合并进去的改动会被丢弃。`,
    },
    base: {
      title: "采用基准版本",
      ok: "采用基准",
      message: `退回冲突发生前的基准版本来解决「${name}」？\n你和对方在这之后的改动都会被丢弃。`,
    },
    "mine-conflict": {
      title: "冲突块采用我的",
      ok: "采用我的",
      message: `「${name}」里冲突的片段采用我的版本，其余已经合并好的内容保留？`,
    },
    "theirs-conflict": {
      title: "冲突块采用对方",
      ok: "采用对方",
      message: `「${name}」里冲突的片段采用对方版本，其余已经合并好的内容保留？`,
    },
    working: {
      title: "保留当前文件",
      ok: "保留当前",
      message: `保留「${name}」现在磁盘上的内容，并标记为已解决？\n如果文件里还有 <<<<<<< 冲突标记，它们会原样留下来。`,
    },
  };
  const item = copy[accept];
  try {
    return await nativeConfirm(item.message, {
      title: item.title,
      kind: "warning",
      okLabel: item.ok,
      cancelLabel: "取消",
    });
  } catch {
    return window.confirm(item.message);
  }
}

async function apply(accept: ConflictAccept) {
  const current = detail.value;
  if (!current || resolving.value || !stillConflict.value) return;
  const ok = await confirmAccept(accept, current.name);
  if (!ok) return;
  const idx = conflicts.value.findIndex((item) => item.path === current.path);
  resolving.value = true;
  actionError.value = "";
  try {
    const res = await api.svnResolveConflict(current.path, accept);
    if (!res.success) {
      actionError.value = [res.stderr, res.stdout].filter(Boolean).join("\n") || "解决失败";
      return;
    }
    emit("changed");
    const items = await api.svnListConflicts(props.root);
    conflicts.value = items;
    const still = items.find((item) => item.path === current.path);
    const next = still || items[idx] || items[idx - 1] || items[0];
    if (next) {
      await selectItem(next.path);
    } else {
      selectedPath.value = "";
      detail.value = null;
    }
  } catch (e) {
    actionError.value = e instanceof Error ? e.message : String(e);
  } finally {
    resolving.value = false;
  }
}

function rowClass(row: SideBySideRow) {
  return `kind-${row.type}`;
}
</script>

<template>
  <div v-if="open" class="conflict-overlay" @mousedown.self="emit('close')">
    <section class="conflict-window" role="dialog" aria-label="解决冲突">
      <header class="conflict-header">
        <div>
          <h3>解决冲突</h3>
          <div class="tiny muted">更新或合并产生冲突后，先选定版本，才能继续提交。</div>
        </div>
        <div class="conflict-header-side">
          <span class="tiny muted">{{ listLoading ? "正在检查..." : `${conflicts.length} 个待处理` }}</span>
          <button class="btn btn-ghost btn-icon" type="button" :disabled="resolving" @click="emit('close')">✕</button>
        </div>
      </header>

      <div v-if="listError" class="conflict-error">{{ listError }}</div>

      <div class="conflict-body">
        <aside class="conflict-list">
          <div v-if="listLoading" class="conflict-empty">正在读取冲突...</div>
          <div v-else-if="!conflicts.length" class="conflict-empty">
            当前范围没有冲突。
            <span>更新后如果出现冲突，可以在这里对比并选择采用哪一侧。</span>
          </div>
          <button
            v-for="item in conflicts"
            :key="item.path"
            type="button"
            class="conflict-item"
            :class="{ active: item.path === selectedPath }"
            :title="item.path"
            @click="selectItem(item.path)"
          >
            <span class="status-badge C">C</span>
            <span class="conflict-item-text">
              <strong>{{ item.name }}</strong>
              <em>{{ item.relativePath }}</em>
              <small>{{ item.kindLabel }}</small>
            </span>
          </button>
        </aside>

        <div class="conflict-detail">
          <div v-if="detailLoading" class="conflict-empty">正在读取冲突内容...</div>
          <div v-else-if="detailError" class="conflict-error">{{ detailError }}</div>
          <div v-else-if="!detail" class="conflict-empty">选择左侧一个冲突文件。</div>
          <template v-else>
            <div class="conflict-summary">
              <div class="conflict-summary-top">
                <strong :title="detail.path">{{ detail.name }}</strong>
                <span class="status-badge C">{{ detail.kindLabel }}</span>
              </div>
              <pre>{{ detail.summary }}</pre>
              <pre v-if="detail.propertyText" class="property-note">{{ detail.propertyText }}</pre>
            </div>

            <div class="conflict-modes">
              <button type="button" :class="{ active: compareMode === 'mine-theirs' }" @click="compareMode = 'mine-theirs'">我的 vs 对方</button>
              <button type="button" :class="{ active: compareMode === 'base-mine' }" :disabled="!canUseBase && compareMode !== 'base-mine'" @click="compareMode = 'base-mine'">基准 vs 我的</button>
              <button type="button" :class="{ active: compareMode === 'working' }" @click="compareMode = 'working'">当前文件</button>
              <span v-if="diffView" class="tiny muted">+{{ diffView.additions }} / -{{ diffView.deletions }}</span>
            </div>

            <div v-if="compareMode === 'working'" class="conflict-preview">
              <div v-if="!detail.working.available" class="conflict-empty">{{ detail.working.message || "没有当前文件内容" }}</div>
              <div v-else class="conflict-code">
                <div
                  v-for="(line, index) in workingLines"
                  :key="index"
                  class="conflict-code-line"
                  :class="markerKind(line)"
                >
                  <span>{{ index + 1 }}</span>
                  <code>{{ line || " " }}</code>
                </div>
                <div v-if="workingTruncated" class="tiny muted conflict-truncated">后面的内容已省略。</div>
              </div>
            </div>

            <div v-else class="conflict-preview">
              <div v-if="previewTooBig" class="conflict-empty">文件较大，跳过逐行对比。可以直接选择下面的解决方式。</div>
              <div v-else-if="!pair?.left.available || !pair?.right.available" class="conflict-split-missing">
                <div>
                  <strong>{{ pair?.leftTitle }}</strong>
                  <p>{{ pair?.left.available ? "这一侧有内容，但另一侧缺失，无法并排对比。可以直接在下面选择版本。" : sideText(pair?.left) }}</p>
                </div>
                <div>
                  <strong>{{ pair?.rightTitle }}</strong>
                  <p>{{ pair?.right.available ? "这一侧有内容，但另一侧缺失，无法并排对比。可以直接在下面选择版本。" : sideText(pair?.right) }}</p>
                </div>
              </div>
              <div v-else class="conflict-diff">
                <div class="conflict-diff-head">
                  <span>{{ pair?.leftTitle }}</span>
                  <span>{{ pair?.rightTitle }}</span>
                </div>
                <div
                  v-for="(row, index) in diffView?.rows || []"
                  :key="index"
                  class="conflict-diff-row"
                  :class="rowClass(row)"
                >
                  <span class="ln">{{ row.left.line ?? "" }}</span>
                  <code>{{ row.left.text || " " }}</code>
                  <span class="ln">{{ row.right.line ?? "" }}</span>
                  <code>{{ row.right.text || " " }}</code>
                </div>
                <div v-if="diffView?.truncated" class="tiny muted conflict-truncated">差异过长，只显示前 {{ MAX_DIFF_ROWS }} 行。</div>
              </div>
            </div>
          </template>
        </div>
      </div>

      <footer class="conflict-footer">
        <div v-if="actionError" class="conflict-error inline">{{ actionError }}</div>
        <div class="conflict-actions">
          <button class="btn" type="button" :disabled="!stillConflict || resolving" @click="apply('mine-full')">采用我的版本</button>
          <button class="btn" type="button" :disabled="!stillConflict || resolving" @click="apply('theirs-full')">采用对方版本</button>
          <button v-if="textConflict" class="btn" type="button" :disabled="!stillConflict || resolving" @click="apply('mine-conflict')">冲突块用我的</button>
          <button v-if="textConflict" class="btn" type="button" :disabled="!stillConflict || resolving" @click="apply('theirs-conflict')">冲突块用对方</button>
          <button v-if="canUseBase" class="btn" type="button" :disabled="!stillConflict || resolving" @click="apply('base')">采用基准版本</button>
          <span class="conflict-actions-gap" />
          <button class="btn" type="button" :disabled="!stillConflict || resolving" @click="apply('working')">保留当前文件</button>
          <button class="btn btn-primary" type="button" :disabled="resolving" @click="emit('close')">完成</button>
        </div>
      </footer>
    </section>
  </div>
</template>
