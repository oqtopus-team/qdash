import type { Theme } from "vitepress";
import DefaultTheme from "vitepress/theme";

import * as OpenApiTheme from "vitepress-openapi/client";
import "vitepress-openapi/dist/style.css";

import Diagram from "./Diagram.vue";
import "./custom.css";
import { REDIRECTS } from "./redirects";

import spec from "../../oas/openapi.json" assert { type: "json" };

/** Where an old page path leads now, or undefined when the path is current. */
function redirectTarget(pathname: string, base: string): string | undefined {
  const path = pathname.startsWith(base) ? `/${pathname.slice(base.length)}` : pathname;
  const key = path.replace(/\.html$/, "").replace(/\/index$/, "/");
  const to = REDIRECTS[key] ?? REDIRECTS[key.replace(/\/$/, "")];
  return to ? `${base}${to.slice(1)}` : undefined;
}

export default {
  extends: DefaultTheme,
  async enhanceApp({ app, router, siteData }) {
    app.component("Diagram", Diagram);

    const openapi = OpenApiTheme.useOpenapi({
      spec,
    });
    OpenApiTheme.theme?.enhanceApp?.({ app, openapi });

    // Pages that moved keep their old links working: the static site serves
    // its 404 page for an old path, and this sends the reader on.
    if (!import.meta.env.SSR) {
      const base = siteData.value.base;
      const to = redirectTarget(window.location.pathname, base);
      if (to) router.go(to + window.location.hash);
      router.onBeforeRouteChange = (href) => {
        const next = redirectTarget(new URL(href, window.location.origin).pathname, base);
        if (next) {
          router.go(next);
          return false;
        }
      };
    }
  },
} satisfies Theme;
