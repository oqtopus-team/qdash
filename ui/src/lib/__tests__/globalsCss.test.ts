import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import tailwindcss from "@tailwindcss/postcss";
import postcss, { type AtRule, type Node, type Rule } from "postcss";
import { describe, expect, it } from "vitest";

const UI_DIR = resolve(__dirname, "../../..");
const GLOBALS_CSS = resolve(UI_DIR, "src/app/globals.css");

describe("globals.css", () => {
  it("compiles to CSS that Turbopack parses, with daisyUI join rules kept", async () => {
    const result = await postcss([tailwindcss({ base: UI_DIR })]).process(
      readFileSync(GLOBALS_CSS, "utf8"),
      { from: GLOBALS_CSS },
    );

    // Tailwind CSS 4.3.4 and 4.3.5 move daisyUI's `.join { @scope (&) { > ... } }` to
    // the top level and keep the relative selector (tailwindlabs/tailwindcss#20668).
    // Lightning CSS, which Turbopack uses, rejects it: `next dev` fails every page with
    // "Invalid empty selector" and `next build` drops the rules.
    const relativeTopLevelSelectors: string[] = [];
    result.root.walkAtRules("scope", (scope: AtRule) => {
      if (scope.parent?.type === "rule") return;
      scope.walkRules((rule: Rule) => {
        // Only rules directly in the scope, or in its @media, have no parent selector.
        let parent: Node | undefined = rule.parent;
        while (parent && parent !== scope && parent.type !== "rule") parent = parent.parent;
        if (parent === scope && /^[>+~]/.test(rule.selector.trim())) {
          relativeTopLevelSelectors.push(rule.selector);
        }
      });
    });
    expect(relativeTopLevelSelectors).toEqual([]);
    expect(result.css).toMatch(/:where\(:focus, :has\(:focus\)\)\s*\{\s*z-index: 2/);
  });
});
