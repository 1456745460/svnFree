<script setup lang="ts">
import { computed, nextTick, ref, watch } from "vue";
import { open } from "@tauri-apps/plugin-dialog";
import type { ProgressState, SvnStatusItem } from "../types";
import { canRevertSvnStatus, getSvnStatusMeta } from "../utils/materialIcon";

const props = defineProps<{
  type: "checkout" | "commit" | "output" | "rename" | "switch" | "changes" | null;
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
}>();

const emit = defineEmits<{
  close: [];
  closeProgress: [];
  checkout: [payload: { url: string; path: string; name?: string }];
  commit: [payload: { message: string; paths: string[] }];
  rename: [newName: string];
  switch: [payload: { url: string }];
  changesAction: [payload: { action: "diff" | "revert" | "commit" | "reveal"; path: string }];
  refreshChanges: [];
}>();

const url = ref("");
const path = ref("");
const name = ref("");
const message = ref("");
const newName = ref("");
const switchUrl = ref("");
const logBox = ref<HTMLElement | null>(null);
const checked = ref<Record<string, boolean>>({});

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

        <div class="field">
          <div class="commit-list-head">
            <label>变更文件</label>
            <div class="commit-list-actions">
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
            <label
              v-for="item in commitItems"
              :key="item.path"
              class="commit-file-row"
              :title="item.path"
            >
              <input
                type="checkbox"
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
              <span class="commit-file-name">{{ item.relativePath || item.name }}</span>
              <span class="tiny muted">{{ item.isDir ? "文件夹" : "文件" }}</span>
            </label>
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
          将仅提交勾选的文件；未纳入版本控制的项会在提交前自动 `svn add`。
        </div>
      </div>
      <div class="modal-footer">
        <button class="btn" :disabled="busy" @click="emit('close')">取消</button>
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
        <div class="field">
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
            <div
              v-for="item in changesItems"
              :key="item.path"
              class="commit-file-row changes-row"
              :title="item.path"
            >
              <span
                v-if="statusMeta(item.status)"
                class="status-badge"
                :class="statusMeta(item.status)!.className"
                :title="statusMeta(item.status)!.label"
              >{{ statusMeta(item.status)!.code }}</span>
              <span v-else class="status-badge other">?</span>
              <span class="commit-file-name">{{ item.relativePath || item.name }}</span>
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
          </div>
        </div>
        <div class="tiny muted">可在此快速浏览本地修改；需要提交时请使用「提交」并勾选文件。</div>
      </div>
      <div class="modal-footer">
        <button class="btn" :disabled="busy" @click="emit('close')">关闭</button>
        <button class="btn btn-primary" :disabled="busy || !(changesItems || []).length" @click="emit('changesAction', { action: 'commit', path: changesRoot || '' })">去提交...</button>
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
