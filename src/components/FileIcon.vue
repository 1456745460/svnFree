<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { getMaterialIconUrl, getSvnStatusMeta } from "../utils/materialIcon";

const props = withDefaults(
  defineProps<{
    name: string;
    isDir?: boolean;
    svnStatus?: string | null;
    size?: "sm" | "md" | "lg";
    expanded?: boolean;
  }>(),
  {
    isDir: false,
    svnStatus: null,
    size: "sm",
    expanded: false,
  },
);

const fallbackUrl = computed(() =>
  getMaterialIconUrl(props.isDir ? "folder" : "file", props.isDir, {
    expanded: props.expanded,
  }),
);

const resolvedUrl = computed(() =>
  getMaterialIconUrl(props.name, props.isDir, { expanded: props.expanded }),
);

const imgSrc = ref(resolvedUrl.value);
const statusMeta = computed(() => getSvnStatusMeta(props.svnStatus));

const rootClass = computed(() => {
  const classes: Record<string, boolean> = {
    [`file-icon--${props.size}`]: true,
    "has-status": Boolean(statusMeta.value),
  };
  if (statusMeta.value) {
    classes[`status-${statusMeta.value.className}`] = true;
  }
  return classes;
});

watch(resolvedUrl, (url) => {
  imgSrc.value = url;
});

function onImgError() {
  if (imgSrc.value !== fallbackUrl.value) {
    imgSrc.value = fallbackUrl.value;
  }
}
</script>

<template>
  <span
    class="file-icon"
    :class="rootClass"
    :data-svn="statusMeta?.code || null"
    :data-svn-class="statusMeta?.className || null"
    :title="statusMeta ? `${name} · ${statusMeta.label} (${statusMeta.code})` : name"
  >
    <img
      class="file-icon__img"
      :src="imgSrc"
      :alt="name"
      draggable="false"
      @error="onImgError"
    />
    <span
      v-if="statusMeta"
      class="file-icon__badge"
      :class="statusMeta.className"
    >{{ statusMeta.code }}</span>
  </span>
</template>
