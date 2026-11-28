<script setup lang="ts">
import { useData } from "vitepress";
import { OASpec, useOpenapi } from "vitepress-openapi/client";

import spec from "../../oas/openapi.json";

// Parse the spec once, when the API reference page first loads it, instead of
// in enhanceApp: VitePress creates a new app for every page it renders, and
// enhanceApp would also ship the spec to readers of every other page.
useOpenapi({ spec });

const { isDark } = useData();
</script>

<template>
  <OASpec :isDark="isDark" />
</template>
