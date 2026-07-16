<script setup lang="ts">
import type { Workspace } from "../types";

defineProps<{
  workspaces: Workspace[];
  activeId: string | null;
  busy: boolean;
}>();

const emit = defineEmits<{
  select: [id: string];
  add: [];
  checkout: [];
  context: [payload: { workspace: Workspace; x: number; y: number }];
}>();

function onContext(ws: Workspace, e: MouseEvent) {
  e.preventDefault();
  e.stopPropagation();
  emit("select", ws.id);
  emit("context", { workspace: ws, x: e.clientX, y: e.clientY });
}
</script>

<template>
  <aside class="panel" @contextmenu.prevent>
    <div class="panel-header">
      <div class="panel-title">工作副本</div>
      <div class="toolbar">
        <button class="btn btn-ghost" title="新增已有工作副本" :disabled="busy" @click="emit('add')">
          新增
        </button>
        <button class="btn btn-primary" title="从 SVN 地址检出" :disabled="busy" @click="emit('checkout')">
          检出
        </button>
      </div>
    </div>

    <div class="panel-body">
      <div v-if="workspaces.length === 0" class="empty-state">
        <strong>暂无工作副本</strong>
        <div class="tiny">点击「新增」添加本地 SVN 目录，或「检出」从仓库下载。</div>
      </div>

      <div v-else class="workspace-list">
        <div
          v-for="ws in workspaces"
          :key="ws.id"
          class="workspace-item"
          :class="{ active: ws.id === activeId }"
          @click="emit('select', ws.id)"
          @contextmenu.prevent.stop="onContext(ws, $event)"
        >
          <div class="workspace-name" :title="ws.path">📁 {{ ws.name }}</div>
        </div>
      </div>
    </div>
  </aside>
</template>
