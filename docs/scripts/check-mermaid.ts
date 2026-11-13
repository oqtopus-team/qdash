// Render every Mermaid diagram of the built documentation site in headless Chromium.
//
// `vitepress build` does not parse Mermaid: vitepress-plugin-mermaid renders diagrams in the
// browser, and a syntax error leaves an empty block on the published page. This check serves
// `.vitepress/dist` under the production base path, opens each page that contains a Mermaid
// fence, and fails unless that page renders one SVG for every fence in its Markdown source.
//
// Usage (from docs/, after `bun run docs:build`): bun run docs:check-mermaid

import { readFileSync, statSync } from "node:fs";
import { join, relative, resolve } from "node:path";
import { chromium } from "playwright";

const DOCS_ROOT = resolve(import.meta.dir, "..");
const DIST_ROOT = join(DOCS_ROOT, ".vitepress", "dist");
const BASE = "/qdash/";
const RENDER_TIMEOUT_MS = 30_000;
// Matches `mermaidPlugin.class` in .vitepress/config.mts.
const BLOCK_SELECTOR = ".vp-doc div.mermaid-diagram";

type Page = { source: string; path: string; expected: number };

/** Count the fences that vitepress-plugin-mermaid renders: info string exactly `mermaid`. */
function countMermaidFences(markdown: string): number {
  let count = 0;
  let open: { char: string; length: number } | null = null;
  for (const line of markdown.split("\n")) {
    const fence = /^ {0,3}(`{3,}|~{3,})(.*)$/.exec(line);
    if (!fence) continue;
    const [, marker, info] = fence;
    if (open === null) {
      open = { char: marker[0], length: marker.length };
      if (info.trim() === "mermaid") count += 1;
    } else if (marker[0] === open.char && marker.length >= open.length && info.trim() === "") {
      open = null;
    }
  }
  return count;
}

function collectPages(): Page[] {
  const pages: Page[] = [];
  const glob = new Bun.Glob("**/*.md");
  for (const file of glob.scanSync({ cwd: DOCS_ROOT })) {
    if (file.startsWith("node_modules/") || file.split("/").some((part) => part.startsWith("."))) {
      continue;
    }
    const expected = countMermaidFences(readFileSync(join(DOCS_ROOT, file), "utf8"));
    if (expected === 0) continue;
    const html = file.replace(/\.md$/, ".html");
    if (!Bun.file(join(DIST_ROOT, html)).size) {
      throw new Error(`${file}: built page ${html} is missing; run \`bun run docs:build\` first`);
    }
    pages.push({ source: file, path: `${BASE}${html}`, expected });
  }
  return pages.sort((a, b) => a.source.localeCompare(b.source));
}

function serveDist() {
  return Bun.serve({
    hostname: "127.0.0.1",
    port: 0,
    fetch(request) {
      const { pathname } = new URL(request.url);
      if (!pathname.startsWith(BASE)) return new Response("Not found", { status: 404 });
      let target = resolve(DIST_ROOT, decodeURIComponent(pathname.slice(BASE.length)));
      if (relative(DIST_ROOT, target).startsWith("..")) {
        return new Response("Forbidden", { status: 403 });
      }
      try {
        if (statSync(target).isDirectory()) target = join(target, "index.html");
      } catch {
        return new Response("Not found", { status: 404 });
      }
      return new Response(Bun.file(target));
    },
  });
}

async function main(): Promise<number> {
  const pages = collectPages();
  const server = serveDist();
  let browser: Awaited<ReturnType<typeof chromium.launch>> | undefined;
  const failures: string[] = [];
  let rendered = 0;

  try {
    browser = await chromium.launch();
    for (const page of pages) {
      const tab = await browser.newPage();
      const errors: string[] = [];
      tab.on("pageerror", (error) => errors.push(error.message));
      tab.on("console", (message) => {
        if (message.type() === "error") errors.push(message.text());
      });

      await tab.goto(new URL(page.path, server.url).href, { waitUntil: "load" });
      // A block that fails to parse never receives an SVG, so a failing page waits for the
      // timeout; a passing page returns as soon as its last diagram renders.
      const settled = await tab
        .waitForFunction(
          ({ selector, expected }) => {
            const blocks = [...document.querySelectorAll(selector)];
            const done = blocks.filter((block) => {
              const svg = block.querySelector("svg");
              return svg !== null && svg.getAttribute("aria-roledescription") !== "error";
            });
            return done.length >= expected;
          },
          { selector: BLOCK_SELECTOR, expected: page.expected },
          { timeout: RENDER_TIMEOUT_MS, polling: 100 },
        )
        .then(() => true)
        .catch(() => false);

      const blocks = await tab.$$eval(BLOCK_SELECTOR, (elements) =>
        elements.map((element) => {
          const svg = element.querySelector("svg");
          return svg !== null && svg.getAttribute("aria-roledescription") !== "error";
        }),
      );
      const ok = blocks.filter(Boolean).length;
      rendered += ok;

      if (!settled || blocks.length !== page.expected || ok !== page.expected) {
        const detail = [...new Set(errors)].map((error) => `    ${error}`).join("\n");
        failures.push(
          `${page.source}: rendered ${ok} of ${page.expected} Mermaid diagrams ` +
            `(${blocks.length} blocks on ${page.path})${detail ? `\n${detail}` : ""}`,
        );
      }
      await tab.close();
    }
  } finally {
    try {
      await browser?.close();
    } finally {
      server.stop(true);
    }
  }

  const expected = pages.reduce((sum, page) => sum + page.expected, 0);
  if (failures.length > 0) {
    console.error(`Mermaid render check failed:\n${failures.join("\n")}`);
    return 1;
  }
  console.log(`Rendered ${rendered} of ${expected} Mermaid diagrams on ${pages.length} pages.`);
  return 0;
}

process.exit(await main());
