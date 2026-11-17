import { readdirSync, readFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";

import tailwindcss from "@tailwindcss/postcss";
import postcss, { type AtRule, type Node, type Rule } from "postcss";
import ts from "typescript";
import { describe, expect, it } from "vitest";

const UI_DIR = resolve(__dirname, "../../..");
const SRC_DIR = resolve(UI_DIR, "src");
const GLOBALS_CSS = resolve(SRC_DIR, "app/globals.css");
// Generated API code never renders form controls.
const SKIPPED_DIRS = new Set(["client", "schemas", "node_modules"]);

const CHOICE_CONTROL = /(^|[\s"'`{])(checkbox|radio|toggle)($|[\s"'`}])/;
const CHOICE_FIELD = /\bchoice-field\b/;
// DaisyUI 5 `.label` is a nowrap, centred, 60%-opacity inline label for text fields.
const DAISY_LABEL = /(^|[\s"'`{])label($|[\s"'`}])/;
// A vertical margin on the control overrides the first-line alignment.
const CONTROL_MARGIN = /(^|[\s"'`{])m[tby]?-/;
const NAMED = new Set(["aria-label", "aria-labelledby"]);

type JsxNode = ts.JsxElement | ts.JsxSelfClosingElement;

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return SKIPPED_DIRS.has(entry.name) ? [] : sourceFiles(path);
    return path.endsWith(".tsx") && !path.includes(".test.") ? [path] : [];
  });
}

/**
 * Lists every DaisyUI checkbox, radio, or toggle whose label does not use the shared `choice-field`
 * rule, and every `choice-field` label that the rule cannot lay out.
 */
function auditChoiceFields(file: string, source: string): string[] {
  const sf = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const opening = (node: JsxNode) => (ts.isJsxElement(node) ? node.openingElement : node);
  const tag = (node: JsxNode) => opening(node).tagName.getText(sf);
  const attributes = (node: JsxNode) =>
    opening(node)
      .attributes.properties.filter(ts.isJsxAttribute)
      .map((prop) => prop.name.getText(sf));
  const classText = (node: JsxNode) => {
    const prop = opening(node).attributes.properties.find(
      (p): p is ts.JsxAttribute => ts.isJsxAttribute(p) && p.name.getText(sf) === "className",
    );
    return prop?.initializer?.getText(sf) ?? "";
  };
  const location = (node: ts.Node) =>
    `${relative(UI_DIR, file)}:${sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1}`;

  const problems: string[] = [];
  const visit = (node: ts.Node, label: ts.JsxElement | null, parent: ts.Node | null) => {
    if (ts.isJsxElement(node) && tag(node) === "label") {
      const cls = classText(node);
      if (CHOICE_FIELD.test(cls) && DAISY_LABEL.test(cls)) {
        problems.push(`${location(node)} drop the DaisyUI label class from a choice-field`);
      }
      node.children.forEach((child) => visit(child, node, node));
      return;
    }
    if (
      (ts.isJsxElement(node) || ts.isJsxSelfClosingElement(node)) &&
      tag(node) === "input" &&
      CHOICE_CONTROL.test(classText(node))
    ) {
      const named = attributes(node).some((name) => NAMED.has(name));
      if (label && CHOICE_FIELD.test(classText(label))) {
        if (parent !== label) {
          problems.push(`${location(node)} make the control a direct child of its choice-field`);
        }
        if (CONTROL_MARGIN.test(classText(node))) {
          problems.push(`${location(node)} remove margin utilities from a choice-field control`);
        }
      } else if (label && !named) {
        problems.push(`${location(node)} use <label className="choice-field"> for this control`);
      } else if (!label && !named) {
        problems.push(`${location(node)} wrap this control in a choice-field label or name it`);
      }
    }
    ts.forEachChild(node, (child) => visit(child, label, node));
  };
  visit(sf, null, null);
  return problems;
}

describe("checkbox, radio, and toggle labels", () => {
  it("wraps every labeled DaisyUI checkbox, radio, and toggle in a choice-field", () => {
    const problems = sourceFiles(SRC_DIR).flatMap((file) =>
      auditChoiceFields(file, readFileSync(file, "utf8")),
    );
    expect(problems).toEqual([]);
  });

  it("reports unshared labels, nested controls, margins, and unnamed controls", () => {
    const source = `
      export const A = () => <label className="flex gap-2"><input type="checkbox" className="checkbox" />A</label>;
      export const B = () => <label className="choice-field"><span><input type="radio" className="radio" /></span>B</label>;
      export const C = () => <label className="choice-field"><input type="checkbox" className="checkbox mt-1" />C</label>;
      export const D = () => <input type="checkbox" className="checkbox checkbox-sm" />;
      export const E = () => <label className="label choice-field"><input type="checkbox" className="checkbox" />E</label>;
      export const F = () => <td><input type="checkbox" className="checkbox" aria-label="Select row" /></td>;
      export const G = () => <label className="choice-field gap-3 p-3"><input type="radio" className="radio radio-sm" /><span>G</span></label>;
      export const H = () => <label className="px-1"><input type="checkbox" className="checkbox" aria-label="Compare" /></label>;
    `;
    const problems = auditChoiceFields(resolve(SRC_DIR, "Fixture.tsx"), source).map((problem) =>
      problem.replace(/^.*Fixture\.tsx:/, ""),
    );
    expect(problems).toEqual([
      '2 use <label className="choice-field"> for this control',
      "3 make the control a direct child of its choice-field",
      "4 remove margin utilities from a choice-field control",
      "5 wrap this control in a choice-field label or name it",
      "6 drop the DaisyUI label class from a choice-field",
    ]);
  });

  it("checks toggle labels and permits the shared toggle pattern", () => {
    const source = `
      const A = () => <label><input type="checkbox" className="toggle toggle-sm" />Enable</label>;
      const B = () => <label className="choice-field"><input type="checkbox" className="toggle toggle-sm" /><span>Enable</span></label>;
    `;
    expect(auditChoiceFields(resolve(SRC_DIR, "Fixture.tsx"), source)).toEqual([
      'src/Fixture.tsx:2 use <label className="choice-field"> for this control',
    ]);
  });

  it("compiles a rule that keeps the control size and aligns it with the first text line", async () => {
    const result = await postcss([tailwindcss({ base: UI_DIR })]).process(
      readFileSync(GLOBALS_CSS, "utf8"),
      { from: GLOBALS_CSS },
    );
    const rules = new Map<string, Map<string, string>>();
    result.root.walkRules((rule: Rule) => {
      if (!rule.selector.includes(".choice-field")) return;
      // Layout utilities on the label must win, so the rule lives in the components layer.
      let layer: AtRule | undefined;
      for (let node: Node | undefined = rule.parent; node; node = node.parent) {
        if (node.type === "atrule" && (node as AtRule).name === "layer") layer = node as AtRule;
      }
      expect(layer?.params, rule.selector).toBe("components");
      const values = rules.get(rule.selector) ?? new Map<string, string>();
      rule.walkDecls((decl) => {
        values.set(decl.prop, decl.value);
      });
      rules.set(rule.selector, values);
    });

    const label = rules.get(".choice-field");
    expect(label?.get("align-items")).toBe("flex-start");
    expect(label?.get("cursor")).toBe("pointer");
    // At least a 24px target (WCAG 2.5.8) for a one-line label of any text size.
    expect(label?.get("padding-block")).toBe("max(0px, calc((1.5rem - 1lh) / 2))");

    const control = rules.get(".choice-field > :is(.checkbox, .radio, .toggle)");
    // Centre the DaisyUI-sized control on the first line box instead of resizing it.
    expect(control?.get("margin-block")).toBe("calc((1lh - var(--size)) / 2)");
    for (const values of rules.values()) {
      expect(values.has("width")).toBe(false);
      expect(values.has("height")).toBe(false);
      expect(values.has("--size")).toBe(false);
    }

    expect(rules.get(".choice-field:has(> input:disabled)")?.get("cursor")).toBe("not-allowed");
    expect(rules.get(".choice-field:has(> input:disabled) > :not(input)")?.get("opacity")).toBe(
      "0.5",
    );
  });
});
