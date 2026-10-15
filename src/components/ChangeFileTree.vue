<script setup lang="ts">
import { computed } from "vue";
import type { SvnStatusItem } from "../types";
import { canRevertSvnStatus, getMaterialIconUrl, getSvnStatusMeta } from "../utils/materialIcon";
import { isUnsupportedDiffPath } from "../utils/diffSupport";
import {
  buildChangeTree,
  flattenChangeTree,
  type ChangeTreeNode,
  type FlatChangeRow,
} from "../utils/changeTree";

const props = defineProps<{
  items: SvnStatusItem[];
  root?: string;
  mode: "commit" | "changes";
  busy?: boolean;
  checked?: Record<string, boolean>;
  collapsed: Record<string, boolean>;
}>();

const emit = defineEmits<{
  toggleCollapse: [key: string];
  toggleCheck: [items: SvnStatusItem[], checked: boolean];
  diff: [path: string];
  reveal: [path: string];
  revert: [path: string];
}>();

const rows = computed(() => flattenChangeTree(buildChangeTree(props.items, props.root), props.collapsed));

function statusMeta(code?: string) {
  return getSvnStatusMeta(code);
}

function checkState(items: SvnStatusItem[]): "all" | "none" | "some" {
  let checkedCount = 0;
  for (const item of items) {
    if (props.checked?.[item.path]) checkedCount++;
  }
  if (checkedCount === 0) return "none";
  if (checkedCount === items.length) return "all";
  return "some";
}

function canDiffItem(item: SvnStatusItem) {
  if (item.status === "D" || item.status === "A") return true;
  return !isUnsupportedDiffPath(item.path, { isDir: item.isDir });
}

function showActions(row: FlatChangeRow) {
  if (!row.node.item) return false;
  if (props.mode === "changes") return true;
  return canDiffItem(row.node.item);
}

function pathSegments(node: ChangeTreeNode): string[] {
  if (!node.isDir || !node.name.includes("/")) return [node.name];
  return node.name.split("/");
}

function iconBaseName(node: ChangeTreeNode) {
  const segments = pathSegments(node);
  return segments[segments.length - 1] || node.name;
}

function iconUrl(row: FlatChangeRow) {
  const expanded = row.node.children.length > 0 && !props.collapsed[row.node.key];
  return getMaterialIconUrl(iconBaseName(row.node), row.node.isDir, { expanded });
}

function onIconError(ev: Event, row: FlatChangeRow) {
  const img = ev.target as HTMLImageElement | null;
  if (!img || img.dataset.fallback === "1") return;
  img.dataset.fallback = "1";
  const expanded = row.node.children.length > 0 && !props.collapsed[row.node.key];
  img.src = getMaterialIconUrl(row.node.isDir ? "folder" : "file", row.node.isDir, { expanded });
}

function onRowClick(row: FlatChangeRow) {
  if (row.node.children.length) emit("toggleCollapse", row.node.key);
}

function rowTitle(node: ChangeTreeNode) {
  return node.item?.path || node.key;
}
</script>

<template>
  <div
    v-for="row in rows"
    :key="row.node.key"
    class="commit-file-row tree-node"
    :class="{
      'tree-folder': row.node.isDir,
      'tree-file': !row.node.isDir,
      'changes-tree-node': mode === 'changes',
      'is-branch': row.node.children.length > 0,
    }"
    :title="rowTitle(row.node)"
    role="treeitem"
    :aria-expanded="row.node.children.length ? !collapsed[row.node.key] : undefined"
    @click="onRowClick(row)"
  >
    <span class="tree-guides" aria-hidden="true">
      <i
        v-for="(kind, index) in row.guides"
        :key="`${row.node.key}-${index}`"
        class="tree-guide"
        :class="kind"
      />
    </span>

    <span
      class="tree-toggle"
      :class="{ collapsed: !!collapsed[row.node.key], 'is-empty': !row.node.children.length }"
      :title="row.node.children.length ? (collapsed[row.node.key] ? '展开' : '合拢') : undefined"
    >
      <i v-if="row.node.children.length" class="tree-chevron" />
    </span>

    <input
      v-if="mode === 'commit'"
      type="checkbox"
      :checked="checkState(row.node.items) === 'all'"
      :indeterminate.prop="checkState(row.node.items) === 'some'"
      :disabled="busy || !row.node.items.length"
      @click.stop
      @change="emit('toggleCheck', row.node.items, ($event.target as HTMLInputElement).checked)"
    />

    <span
      v-if="row.node.item && statusMeta(row.node.item.status)"
      class="status-badge"
      :class="statusMeta(row.node.item.status)!.className"
      :title="statusMeta(row.node.item.status)!.label"
    >{{ statusMeta(row.node.item.status)!.code }}</span>
    <span v-else class="status-badge tree-badge-slot" aria-hidden="true"></span>

    <img class="tree-node-icon" :src="iconUrl(row)" alt="" draggable="false" @error="onIconError($event, row)" />

    <span class="tree-label">
      <span class="commit-file-name">
        <template v-for="(segment, index) in pathSegments(row.node)" :key="`${row.node.key}-${index}`">
          <span v-if="index > 0" class="tree-path-sep">/</span>{{ segment }}
        </template>
      </span>
      <span v-if="row.node.isDir && row.node.items.length > 1" class="tiny muted tree-count">
        {{ row.node.items.length }} 个
      </span>
    </span>

    <div v-if="row.node.item && showActions(row)" class="changes-actions" @click.stop>
      <button
        v-if="mode === 'changes' || canDiffItem(row.node.item)"
        type="button"
        class="btn btn-ghost tiny-btn"
        :disabled="busy"
        @click="emit('diff', row.node.item.path)"
      >DIFF</button>
      <template v-if="mode === 'changes'">
        <button
          type="button"
          class="btn btn-ghost tiny-btn"
          :disabled="busy"
          @click="emit('reveal', row.node.item.path)"
        >定位</button>
        <button
          v-if="canRevertSvnStatus(row.node.item.status)"
          type="button"
          class="btn btn-ghost tiny-btn danger-text"
          :disabled="busy"
          @click="emit('revert', row.node.item.path)"
        >还原</button>
      </template>
    </div>
    <span v-else class="tree-actions-spacer" />
  </div>
</template>
