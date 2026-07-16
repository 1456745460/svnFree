<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { marked } from "marked";
import type { PreviewPayload } from "../types";
import { guessLanguageFromPath, highlightCode, highlightCodeFromPath } from "../utils/codeHighlight";

const props = defineProps<{
  preview: PreviewPayload | null;
  busy: boolean;
  collapsed?: boolean;
}>();

const emit = defineEmits<{
  "toggle-collapse": [];
}>();

const lightboxOpen = ref(false);
const scale = ref(1);
const offsetX = ref(0);
const offsetY = ref(0);
const dragging = ref(false);

const MIN_SCALE = 0.2;
const MAX_SCALE = 8;

let dragState: { startX: number; startY: number; originX: number; originY: number; moved: boolean } | null =
  null;
let suppressClickUntil = 0;

type MdViewMode = "preview" | "source";
const mdViewMode = ref<MdViewMode>("preview");

function readMdViewPref(): MdViewMode {
  try {
    const v = localStorage.getItem("sf.preview.mdMode");
    return v === "source" ? "source" : "preview";
  } catch {
    return "preview";
  }
}

function setMdViewMode(mode: MdViewMode) {
  mdViewMode.value = mode;
  try {
    localStorage.setItem("sf.preview.mdMode", mode);
  } catch {
    // ignore
  }
}

function formatSize(size: number) {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(2)} MB`;
}

function resetTransform() {
  scale.value = 1;
  offsetX.value = 0;
  offsetY.value = 0;
  dragging.value = false;
  dragState = null;
}

function openLightbox() {
  if (!(props.preview?.kind === "image" && props.preview.dataUrl)) return;
  resetTransform();
  lightboxOpen.value = true;
}

function closeLightbox() {
  lightboxOpen.value = false;
  resetTransform();
  endDrag();
}

function onLightboxWheel(e: WheelEvent) {
  e.preventDefault();
  const delta = e.deltaY > 0 ? -0.12 : 0.12;
  const prev = scale.value;
  const next = Math.min(MAX_SCALE, Math.max(MIN_SCALE, Number((prev + delta).toFixed(2))));
  if (next === prev) return;

  // 以鼠标位置为中心缩放，尽量保持视点稳定
  const stage = (e.currentTarget as HTMLElement | null)?.querySelector?.(
    ".image-lightbox-stage",
  ) as HTMLElement | null;
  if (stage) {
    const rect = stage.getBoundingClientRect();
    const cx = e.clientX - rect.left - rect.width / 2;
    const cy = e.clientY - rect.top - rect.height / 2;
    const ratio = next / prev;
    offsetX.value = cx - (cx - offsetX.value) * ratio;
    offsetY.value = cy - (cy - offsetY.value) * ratio;
  }

  scale.value = next;
  // 缩回 1 附近时复位偏移，避免越缩越偏
  if (next <= 1.01) {
    offsetX.value = 0;
    offsetY.value = 0;
  }
}

function onPointerDown(e: PointerEvent) {
  if (e.button !== 0) return;
  // 仅在放大后允许拖拽查看
  if (scale.value <= 1.01) return;
  e.preventDefault();
  e.stopPropagation();
  dragState = {
    startX: e.clientX,
    startY: e.clientY,
    originX: offsetX.value,
    originY: offsetY.value,
    moved: false,
  };
  dragging.value = true;
  try {
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  } catch {
    // ignore
  }
  window.addEventListener("pointermove", onPointerMove);
  window.addEventListener("pointerup", onPointerUp);
  window.addEventListener("pointercancel", onPointerUp);
}

function onPointerMove(e: PointerEvent) {
  if (!dragState) return;
  const dx = e.clientX - dragState.startX;
  const dy = e.clientY - dragState.startY;
  if (!dragState.moved && Math.hypot(dx, dy) > 3) dragState.moved = true;
  offsetX.value = dragState.originX + dx;
  offsetY.value = dragState.originY + dy;
}

function endDrag() {
  window.removeEventListener("pointermove", onPointerMove);
  window.removeEventListener("pointerup", onPointerUp);
  window.removeEventListener("pointercancel", onPointerUp);
  dragging.value = false;
  dragState = null;
}

function onPointerUp() {
  if (dragState?.moved) {
    // 防止拖拽结束后误触发 click 关闭
    suppressClickUntil = Date.now() + 200;
  }
  endDrag();
}

function onStageClick(e: MouseEvent) {
  if (Date.now() < suppressClickUntil) {
    e.preventDefault();
    e.stopPropagation();
    return;
  }
  // 点击空白关闭；点在图片上不关闭
  if ((e.target as HTMLElement | null)?.classList?.contains("image-lightbox-img")) return;
  closeLightbox();
}

function onKey(e: KeyboardEvent) {
  if (!lightboxOpen.value) return;
  if (e.key === "Escape") {
    e.preventDefault();
    closeLightbox();
  }
}

const imgStyle = computed(() => ({
  transform: `translate(${offsetX.value}px, ${offsetY.value}px) scale(${scale.value})`,
  cursor: scale.value > 1.01 ? (dragging.value ? "grabbing" : "grab") : "default",
}));

const textLanguage = computed(() => {
  if (!(props.preview?.kind === "text" && props.preview.path)) return "plaintext";
  return guessLanguageFromPath(props.preview.path);
});

const highlightedHtml = computed(() => {
  if (!(props.preview?.kind === "text" && props.preview.content != null)) return "";
  return highlightCodeFromPath(props.preview.content, props.preview.path);
});

const isMarkdown = computed(() => {
  if (!(props.preview?.kind === "text" && props.preview.path)) return false;
  return textLanguage.value === "markdown";
});

const renderedMarkdownHtml = computed(() => {
  if (!(isMarkdown.value && props.preview?.content != null)) return "";
  try {
    const raw = marked.parse(props.preview.content, {
      async: false,
      gfm: true,
      breaks: false,
    }) as string;
    // 为代码块补充语法高亮
    return raw.replace(
      /<pre><code(?: class="language-([^"]*)")?>([\s\S]*?)<\/code><\/pre>/g,
      (_m, lang: string | undefined, code: string) => {
        const decoded = code
          .replace(/&lt;/g, "<")
          .replace(/&gt;/g, ">")
          .replace(/&amp;/g, "&")
          .replace(/&quot;/g, '"')
          .replace(/&#39;/g, "'");
        const language = (lang || "").trim() || "plaintext";
        const highlighted = highlightCode(decoded, language);
        const cls = language && language !== "plaintext" ? ` class="language-${language} hljs"` : ' class="hljs"';
        return `<pre><code${cls}>${highlighted}</code></pre>`;
      },
    );
  } catch {
    return `<pre class="preview-code">${props.preview.content
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")}</pre>`;
  }
});

const isCollapsed = computed(() => !!props.collapsed);

// 初始化 markdown 视图偏好
mdViewMode.value = readMdViewPref();

watch(
  () => props.preview?.path,
  () => {
    if (lightboxOpen.value) closeLightbox();
  },
);

watch(lightboxOpen, (v) => {
  if (v) window.addEventListener("keydown", onKey, true);
  else window.removeEventListener("keydown", onKey, true);
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey, true);
  endDrag();
});
</script>

<template>
  <aside class="panel preview-panel relative" :class="{ collapsed: isCollapsed }">
    <div v-if="busy && !isCollapsed" class="loading-overlay"><div class="spinner" /></div>

    <template v-if="!isCollapsed">
      <div class="panel-header preview-header">
        <div class="panel-title">预览</div>
        <button
          type="button"
          class="btn btn-ghost btn-icon preview-toggle"
          title="收起预览区"
          @click="emit('toggle-collapse')"
        >
          »
        </button>
      </div>
      <div v-if="!preview" class="empty-state">
        <strong>未选择文件</strong>
        <div class="tiny">点击文件或文件夹后，在此预览内容。</div>
      </div>

      <template v-else>
        <div class="preview-meta">
          <div class="preview-meta-top">
            <div class="preview-meta-main">
              <h3>{{ preview.name }}</h3>
              <div class="tiny muted">{{ preview.path }}</div>
              <div class="tiny muted" style="margin-top: 6px">
                {{ preview.kind === "directory" ? "文件夹" : formatSize(preview.size) }}
                <span v-if="preview.mime"> · {{ preview.mime }}</span>
                <span v-if="preview.kind === 'text' && textLanguage !== 'plaintext'">
                  · {{ textLanguage }}
                </span>
              </div>
            </div>
            <div v-if="isMarkdown" class="preview-md-toggle view-toggle" title="Markdown 预览模式">
              <button
                type="button"
                :class="{ active: mdViewMode === 'preview' }"
                @click="setMdViewMode('preview')"
              >
                渲染
              </button>
              <button
                type="button"
                :class="{ active: mdViewMode === 'source' }"
                @click="setMdViewMode('source')"
              >
                源码
              </button>
            </div>
          </div>
        </div>

        <div class="preview-content preview-selectable">
          <div v-if="preview.kind === 'image' && preview.dataUrl" class="preview-image-wrap">
            <img
              class="preview-image-thumb"
              :src="preview.dataUrl"
              :alt="preview.name"
              title="点击放大查看"
              @click="openLightbox"
            />
            <div class="tiny muted preview-image-hint">
              点击放大 · 滚轮缩放 · 放大后拖拽查看 · Esc/右上角关闭
            </div>
          </div>
          <div
            v-else-if="isMarkdown && preview.content != null && mdViewMode === 'preview'"
            class="markdown-body"
            v-html="renderedMarkdownHtml"
          />
          <pre
            v-else-if="preview.kind === 'text' && preview.content != null"
            class="preview-code hljs"
            v-html="highlightedHtml"
          />
          <div v-else class="empty-state" style="height: auto; padding: 24px 0">
            <strong>{{ preview.message || "无法预览" }}</strong>
            <div class="tiny" v-if="preview.kind === 'directory'">可双击进入该文件夹。</div>
          </div>
        </div>
      </template>
    </template>

    <button
      v-else
      type="button"
      class="preview-collapsed-rail"
      title="展开预览区"
      @click="emit('toggle-collapse')"
    >
      <span class="preview-collapsed-expand">«</span>
      <span class="preview-collapsed-label">预览</span>
    </button>

    <div
      v-if="lightboxOpen && preview?.kind === 'image' && preview.dataUrl"
      class="image-lightbox"
      :class="{ dragging }"
      @wheel.prevent="onLightboxWheel"
    >
      <button type="button" class="image-lightbox-close" title="关闭" @click="closeLightbox">✕</button>
      <div class="image-lightbox-stage" @click="onStageClick">
        <img
          class="image-lightbox-img"
          :class="{ grabable: scale > 1.01, dragging }"
          :src="preview.dataUrl"
          :alt="preview.name"
          :style="imgStyle"
          draggable="false"
          @pointerdown="onPointerDown"
          @click.stop
        />
      </div>
      <div class="image-lightbox-meta">
        {{ preview.name }} · {{ Math.round(scale * 100) }}%
        <span v-if="scale > 1.01"> · 拖拽可平移</span>
      </div>
    </div>
  </aside>
</template>
