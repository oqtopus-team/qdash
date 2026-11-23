import { readdirSync, readFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";

import postcss, { type Rule } from "postcss";
import { describe, expect, it } from "vitest";

const UI_DIR = resolve(__dirname, "../../..");
const SRC_DIR = resolve(UI_DIR, "src");
const GLOBALS_CSS = resolve(SRC_DIR, "app/globals.css");
// Generated API code carries no styling.
const SKIPPED_DIRS = new Set(["client", "schemas", "node_modules", "__tests__"]);

function sourceFiles(dir: string, extensions: string[]): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      return SKIPPED_DIRS.has(entry.name) ? [] : sourceFiles(path, extensions);
    }
    return extensions.some((ext) => path.endsWith(ext)) ? [path] : [];
  });
}

// DaisyUI 4 exposed theme colors as bare channels (`--p`, `--b1`, ...). DaisyUI 5 removed them,
// so `oklch(var(--p))` resolves to nothing and the element silently loses its color.
const LEGACY_THEME_VAR =
  /\b(?:oklch|hsl)\(\s*var\(--(?:p|pc|s|sc|a|ac|n|nc|b1|b2|b3|bc|in|su|wa|er)\)/;

// A className string literal or template chunk that contains the `btn` component class.
const BTN_CLASS_STRING = /["'`]((?:[^"'`\n]*\s)?btn(?:\s[^"'`\n]*)?)["'`]/g;
const ROUNDED_UTILITY = /(?:^|\s)rounded-(?:none|sm|md|lg|xl|2xl|3xl|full)(?=\s|$)/;

describe("design tokens", () => {
  it("uses DaisyUI 5 color variables instead of removed DaisyUI 4 channels", () => {
    const offenders = sourceFiles(SRC_DIR, [".ts", ".tsx", ".css"]).flatMap((file) =>
      readFileSync(file, "utf8")
        .split("\n")
        .flatMap((line, index) =>
          LEGACY_THEME_VAR.test(line) ? [`${relative(UI_DIR, file)}:${index + 1}`] : [],
        ),
    );
    expect(offenders).toEqual([]);
  });

  it("keeps the full radius on .btn-circle when globals.css sets button radii", () => {
    const root = postcss.parse(readFileSync(GLOBALS_CSS, "utf8"), { from: GLOBALS_CSS });
    const unguarded: string[] = [];
    root.walkRules((rule: Rule) => {
      const setsRadius = rule.nodes.some(
        (node) => node.type === "decl" && node.prop === "border-radius",
      );
      if (!setsRadius) return;
      for (const selector of rule.selectors) {
        if (
          /\.btn(?:-xs|-sm|-md|-lg|-xl)?(?![\w-])/.test(selector) &&
          !/btn-circle/.test(selector)
        ) {
          unguarded.push(selector);
        }
      }
    });
    expect(unguarded).toEqual([]);
  });

  it("leaves button radii to the theme rule instead of rounded-* utilities", () => {
    // globals.css sets the radius of every non-circle `.btn` outside a layer, so a rounded-*
    // utility on a button never applies and only misstates the rendered shape.
    const offenders = sourceFiles(SRC_DIR, [".tsx"]).flatMap((file) => {
      const source = readFileSync(file, "utf8");
      return [...source.matchAll(BTN_CLASS_STRING)]
        .filter((match) => ROUNDED_UTILITY.test(match[1]))
        .map((match) => `${relative(UI_DIR, file)}: ${match[1].trim()}`);
    });
    expect(offenders).toEqual([]);
  });
});
