import type { Theme } from "vitepress";
import DefaultTheme from "vitepress/theme";

import * as OpenApiTheme from "vitepress-openapi";
import "vitepress-openapi/dist/style.css";

import "./custom.css";

import spec from "../../oas/openapi.json" assert { type: "json" };

export default {
  extends: DefaultTheme,
  async enhanceApp({ app, router, siteData }) {
    const openapi = OpenApiTheme.useOpenapi({
      spec,
    });
    OpenApiTheme.theme?.enhanceApp?.({ app, openapi });
  },
} satisfies Theme;
