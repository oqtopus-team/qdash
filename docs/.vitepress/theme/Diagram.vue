<script setup lang="ts">
import { computed } from "vue";

// Diagrams are inlined rather than loaded through <img> so their CSS can read
// the theme variables and follow the light/dark switch.
const sources = import.meta.glob<string>("../../diagrams/*.svg", {
  query: "?raw",
  import: "default",
  eager: true,
});

const props = defineProps<{ name: string; caption?: string }>();

const svg = computed(() => {
  const source = sources[`../../diagrams/${props.name}.svg`];
  if (!source) throw new Error(`Unknown diagram: ${props.name}`);
  return source;
});
</script>

<template>
  <figure class="qd-diagram">
    <div v-html="svg" />
    <figcaption v-if="caption">{{ caption }}</figcaption>
  </figure>
</template>

<style scoped>
.qd-diagram {
  margin: 24px 0;
}
.qd-diagram :deep(svg) {
  display: block;
  width: 100%;
  height: auto;
}
.qd-diagram figcaption {
  margin-top: 8px;
  font-size: 14px;
  color: var(--vp-c-text-2);
  text-align: center;
}
</style>
