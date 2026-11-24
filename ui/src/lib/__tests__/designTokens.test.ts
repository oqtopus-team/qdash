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

function hexChannels(hex: string): number[] {
  return [1, 3, 5].map((i) => {
    const c = parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  });
}

function contrastRatio(a: string, b: string): number {
  const luminance = (hex: string) => {
    const [r, g, bl] = hexChannels(hex);
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl;
  };
  const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
  return (hi + 0.05) / (lo + 0.05);
}

function oklchHue(hex: string): number {
  const [r, g, b] = hexChannels(hex);
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  const A = 1.9779984951 * l - 2.428592205 * m + 0.4505937099 * s;
  const B = 0.0259040371 * l + 0.7827717662 * m - 0.808675766 * s;
  return ((Math.atan2(B, A) * 180) / Math.PI + 360) % 360;
}

// Custom color tokens declared by the QDash light or dark theme rule in globals.css.
function themeTokens(theme: "light" | "dark"): Record<string, string> {
  const root = postcss.parse(readFileSync(GLOBALS_CSS, "utf8"), { from: GLOBALS_CSS });
  const tokens: Record<string, string> = {};
  root.walkRules((rule: Rule) => {
    if (!rule.selectors.includes(`[data-theme="${theme}"]`)) return;
    rule.walkDecls(/^--color-/, (decl) => {
      tokens[decl.prop] = decl.value.trim();
    });
  });
  return tokens;
}

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

  it.each(["light", "dark"] as const)(
    "keeps the %s info color readable and clearly apart from success",
    (theme) => {
      const tokens = themeTokens(theme);
      const info = tokens["--color-info"];
      // Running uses info and completed uses success; a teal info read as green beside it.
      for (const surface of ["--color-base-100", "--color-base-200", "--color-info-content"]) {
        expect(contrastRatio(info, tokens[surface])).toBeGreaterThanOrEqual(4.5);
      }
      const hueGap = Math.abs(oklchHue(info) - oklchHue(tokens["--color-success"]));
      expect(Math.min(hueGap, 360 - hueGap)).toBeGreaterThanOrEqual(80);
    },
  );
});
