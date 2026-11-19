import { readdirSync, readFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";

import type { CSSObjectWithLabel, ControlProps, GroupBase } from "react-select";
import { describe, expect, it } from "vitest";

import { getDaisySelectStyles, SELECT_CONTROL_HEIGHT } from "../react-select-theme";

const UI_DIR = resolve(__dirname, "../../..");
const SRC_DIR = resolve(UI_DIR, "src");

type Option = { value: string; label: string };

function controlStyle(isMulti: boolean) {
  const styles = getDaisySelectStyles<Option, boolean, GroupBase<Option>>();
  const state = { isFocused: false, isMulti } as ControlProps<Option, boolean, GroupBase<Option>>;
  return styles.control?.({} as CSSObjectWithLabel, state);
}

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) {
      return ["client", "schemas", "node_modules"].includes(entry.name) ? [] : sourceFiles(path);
    }
    return /\.tsx?$/.test(path) && !path.includes(".test.") ? [path] : [];
  });
}

describe("React-Select theme", () => {
  it("sizes a single select like a default DaisyUI input, select, or button", () => {
    expect(SELECT_CONTROL_HEIGHT).toBe("calc(var(--size-field, 0.25rem) * 10)");
    expect(controlStyle(false)).toMatchObject({
      minHeight: SELECT_CONTROL_HEIGHT,
      height: SELECT_CONTROL_HEIGHT,
    });
  });

  it("lets a multi-select grow from the same minimum height", () => {
    expect(controlStyle(true)).toMatchObject({ minHeight: SELECT_CONTROL_HEIGHT, height: "auto" });
  });

  it("uses DaisyUI 5 theme variables, not the removed DaisyUI 4 ones", () => {
    const source = readFileSync(resolve(SRC_DIR, "lib/react-select-theme.ts"), "utf8");
    expect(source).not.toMatch(/var\(--(b[123]|bc|p|pc|er|rounded-[a-z]+)\b/);
  });

  it("keeps control heights out of call sites and global CSS", () => {
    const problems = sourceFiles(SRC_DIR).flatMap((file) => {
      const source = readFileSync(file, "utf8");
      if (!source.includes("react-select") || file.endsWith("react-select-theme.ts")) return [];
      // Style functions for the parts that set a control's height.
      const blocks = source.matchAll(
        /\b(control|valueContainer|indicatorsContainer):\s*\([^)]*\)\s*=>\s*\(\{([^}]*)\}\)/g,
      );
      return [...blocks]
        .filter((block) => /\b(minHeight|height):\s*"?\d/.test(block[2]))
        .map((block) => {
          const line = source.slice(0, block.index).split("\n").length;
          return `${relative(UI_DIR, file)}:${line}`;
        });
    });
    expect(problems).toEqual([]);

    const css = readFileSync(resolve(SRC_DIR, "app/globals.css"), "utf8");
    const controlRules = css.match(/[^{}]*-control"\][^{]*\{[^}]*\}/g) ?? [];
    expect(controlRules.length).toBeGreaterThan(0);
    for (const rule of controlRules) {
      expect(rule).not.toMatch(/min-height|(^|[\s;{])height/);
      // `form-control` and other plain classes ending in -control are not React-Select.
      expect(rule).toContain('[class*="css-"]');
    }
  });
});
