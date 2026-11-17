import { readdirSync, readFileSync } from "node:fs";
import { join, relative, resolve } from "node:path";

import tailwindcss from "@tailwindcss/postcss";
import postcss, { type Rule } from "postcss";
import ts from "typescript";
import { describe, expect, it } from "vitest";

const UI_DIR = resolve(__dirname, "../../..");
const SRC_DIR = resolve(UI_DIR, "src");
const GLOBALS_CSS = resolve(SRC_DIR, "app/globals.css");
// Generated API code never renders buttons.
const SKIPPED_DIRS = new Set(["client", "schemas", "node_modules"]);

const BTN_CLASS = /(^|[\s"'`{])btn($|[\s"'`}])/;
const ICON_ONLY_CLASS = /\bbtn-(square|circle)\b/;
// Start-aligned rows (sidebar items, disclosure headers) align icons to a list edge, not
// to a centered label, so the optical rule does not apply to them.
const ALIGNED_ROW_CLASS = /\bjustify-(start|between|end)\b/;

type JsxNode = ts.JsxElement | ts.JsxSelfClosingElement;
type Child = { kind: "icon"; icons: JsxNode[] } | { kind: "label" } | { kind: "optional" };

function sourceFiles(dir: string): string[] {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return SKIPPED_DIRS.has(entry.name) ? [] : sourceFiles(path);
    return path.endsWith(".tsx") && !path.includes(".test.") ? [path] : [];
  });
}

/**
 * Lists every icon at the start or end of a labeled `.btn` that lacks the matching
 * `data-icon` hook, and every hook placed where the shared spacing rule cannot apply.
 */
function auditButtonIcons(file: string, source: string): string[] {
  const sf = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
  const lucideNames = new Set<string>();
  const otherImports = new Set<string>();
  for (const statement of sf.statements) {
    if (!ts.isImportDeclaration(statement) || !statement.importClause) continue;
    const target =
      (statement.moduleSpecifier as ts.StringLiteral).text === "lucide-react"
        ? lucideNames
        : otherImports;
    if (statement.importClause.name) target.add(statement.importClause.name.text);
    const bindings = statement.importClause.namedBindings;
    if (bindings && ts.isNamedImports(bindings)) {
      for (const element of bindings.elements) target.add(element.name.text);
    }
  }

  const opening = (node: JsxNode) => (ts.isJsxElement(node) ? node.openingElement : node);
  const attribute = (node: JsxNode, name: string) =>
    opening(node).attributes.properties.find(
      (prop): prop is ts.JsxAttribute => ts.isJsxAttribute(prop) && prop.name.getText(sf) === name,
    );
  const classText = (node: JsxNode) => attribute(node, "className")?.initializer?.getText(sf) ?? "";
  const dataIcon = (node: JsxNode) => {
    const init = attribute(node, "data-icon")?.initializer;
    return init && ts.isStringLiteral(init) ? init.text : undefined;
  };
  const location = (node: ts.Node) =>
    `${relative(UI_DIR, file)}:${sf.getLineAndCharacterOfPosition(node.getStart(sf)).line + 1}`;

  const isIcon = (node: ts.Node): node is JsxNode => {
    if (!ts.isJsxElement(node) && !ts.isJsxSelfClosingElement(node)) return false;
    const tag = opening(node).tagName.getText(sf);
    if ((tag === "span" || tag === "div") && /\bloading\b/.test(classText(node))) return true;
    if (tag === "svg") return true;
    if (!ts.isJsxSelfClosingElement(node)) return false;
    return lucideNames.has(tag) || (/^([A-Z]\w*)?Icon$/.test(tag) && !otherImports.has(tag));
  };

  const unwrap = (expr: ts.Expression): ts.Expression =>
    ts.isParenthesizedExpression(expr) ? unwrap(expr.expression) : expr;

  // Returns the icons an expression can render, or null when it can render anything else.
  const iconBranches = (raw: ts.Expression): JsxNode[] | null => {
    const expr = unwrap(raw);
    if (expr.kind === ts.SyntaxKind.NullKeyword || expr.kind === ts.SyntaxKind.FalseKeyword) {
      return [];
    }
    if (isIcon(expr)) return [expr];
    if (ts.isConditionalExpression(expr)) {
      const whenTrue = iconBranches(expr.whenTrue);
      const whenFalse = iconBranches(expr.whenFalse);
      return whenTrue && whenFalse ? [...whenTrue, ...whenFalse] : null;
    }
    if (
      ts.isBinaryExpression(expr) &&
      expr.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken
    ) {
      return iconBranches(expr.right);
    }
    return null;
  };

  const classify = (child: ts.JsxChild): Child | null => {
    if (ts.isJsxText(child)) return child.text.trim() ? { kind: "label" } : null;
    if (ts.isJsxExpression(child)) {
      if (!child.expression) return null;
      const icons = iconBranches(child.expression);
      if (icons?.length) return { kind: "icon", icons };
      const expr = unwrap(child.expression);
      // `{open && <span>Label</span>}` can leave the icon alone, so it is not a label.
      const optional =
        ts.isBinaryExpression(expr) &&
        expr.operatorToken.kind === ts.SyntaxKind.AmpersandAmpersandToken;
      return optional ? { kind: "optional" } : { kind: "label" };
    }
    return isIcon(child) ? { kind: "icon", icons: [child] } : { kind: "label" };
  };

  // Expand fragments and ternaries into the direct children React actually renders.
  const variants = (nodes: readonly ts.JsxChild[]): ts.JsxChild[][] => {
    let result: ts.JsxChild[][] = [[]];
    for (const node of nodes) {
      let choices: ts.JsxChild[][] = [[node]];
      if (ts.isJsxFragment(node)) choices = variants(node.children);
      else if (ts.isJsxExpression(node) && node.expression) {
        const expr = unwrap(node.expression);
        if (ts.isConditionalExpression(expr)) {
          choices = [expr.whenTrue, expr.whenFalse].flatMap((branch) => {
            const value = unwrap(branch);
            return ts.isJsxFragment(value)
              ? variants(value.children)
              : ts.isJsxElement(value) || ts.isJsxSelfClosingElement(value)
                ? [[value]]
                : [[ts.factory.createJsxExpression(undefined, value)]];
          });
        }
      }
      result = result.flatMap((prefix) => choices.map((choice) => [...prefix, ...choice]));
    }
    return result;
  };

  const problems: string[] = [];
  const visit = (node: ts.Node) => {
    if (
      ts.isJsxElement(node) &&
      BTN_CLASS.test(classText(node)) &&
      !ALIGNED_ROW_CLASS.test(classText(node))
    ) {
      const iconOnly = ICON_ONLY_CLASS.test(classText(node));
      for (const rendered of variants(node.children)) {
        const children = rendered.map(classify).filter((child) => child !== null);
        const labeled = children.some((child) => child.kind === "label");
        const expected = new Map<JsxNode, string>();
        if (!iconOnly && labeled && children.length > 1) {
          const first = children[0];
          const last = children[children.length - 1];
          if (first.kind === "icon")
            first.icons.forEach((icon) => expected.set(icon, "inline-start"));
          if (last.kind === "icon") last.icons.forEach((icon) => expected.set(icon, "inline-end"));
        }
        if (expected.size) {
          for (const child of rendered) {
            if (
              (ts.isJsxElement(child) || ts.isJsxSelfClosingElement(child)) &&
              /\b(?:m[lrsex]?|gap|space-x)-/.test(classText(child))
            ) {
              problems.push(`${location(child)} remove spacing utilities from button children`);
            }
          }
        }
        for (const child of children) {
          if (child.kind !== "icon") continue;
          for (const icon of child.icons) {
            const want = expected.get(icon);
            const have = dataIcon(icon);
            if (want !== have) {
              problems.push(
                `${location(icon)} expected data-icon=${want ?? "(none)"}, found ${have}`,
              );
            }
          }
        }
      }
    }
    ts.forEachChild(node, visit);
  };
  visit(sf);
  return [...new Set(problems)];
}

describe("button icon spacing", () => {
  it("hooks every leading and trailing icon of a labeled .btn with data-icon", () => {
    const problems = sourceFiles(SRC_DIR).flatMap((file) =>
      auditButtonIcons(file, readFileSync(file, "utf8")),
    );
    expect(problems).toEqual([]);
  });

  it("reports missing, misplaced, and icon-only hooks", () => {
    const source = `
      import { ChevronDown, Plus, X } from "lucide-react";
      export const A = () => <button className="btn"><Plus />Add</button>;
      export const B = () => <button className="btn">Next<ChevronDown data-icon="inline-start" /></button>;
      export const C = () => <button className="btn btn-square"><X data-icon="inline-start" /></button>;
      export const D = (p: { busy: boolean }) => (
        <button className="btn">
          {p.busy ? <span className="loading loading-spinner" /> : <Plus data-icon="inline-start" />}
          Save
        </button>
      );
      export const E = (p: { open: boolean }) => (
        <button className="btn"><Plus />{p.open && <span>Add</span>}</button>
      );
      export const F = () => (
        <button className="btn"><Plus data-icon="inline-start" />Add<ChevronDown data-icon="inline-end" /></button>
      );
      export const G = () => <button className="btn w-full justify-start"><Plus />Row</button>;
    `;
    const problems = auditButtonIcons(resolve(SRC_DIR, "Fixture.tsx"), source).map((problem) =>
      problem.replace(/^.*Fixture\.tsx:/, ""),
    );
    expect(problems).toEqual([
      "3 expected data-icon=inline-start, found undefined",
      "4 expected data-icon=inline-end, found inline-start",
      "5 expected data-icon=(none), found inline-start",
      "8 expected data-icon=inline-start, found undefined",
    ]);
  });

  it("checks conditional fragments and redundant child margins", () => {
    const source = `
      import { Plus } from "lucide-react";
      const A = ({busy}) => <button className="btn">{busy
        ? <><span className="loading" />Saving</>
        : <><Plus />Save</>}</button>;
      const B = () => <button className="btn"><Plus data-icon="inline-start" className="mr-2" />
<span className="ml-1">Add</span></button>;
    `;
    const problems = auditButtonIcons(resolve(SRC_DIR, "Fixture.tsx"), source);
    expect(problems.filter((problem) => problem.includes("expected data-icon"))).toHaveLength(2);
    expect(problems.filter((problem) => problem.includes("remove spacing"))).toHaveLength(2);
  });

  it("compiles the shared rule so only the icon side of a text button loses padding", async () => {
    const result = await postcss([tailwindcss({ base: UI_DIR })]).process(
      readFileSync(GLOBALS_CSS, "utf8"),
      { from: GLOBALS_CSS },
    );
    const declarations = new Map<string, Map<string, string>>();
    result.root.walkRules((rule: Rule) => {
      if (!rule.selector.includes("data-icon") && !rule.selector.includes("lucide-play")) return;
      const values = declarations.get(rule.selector) ?? new Map<string, string>();
      rule.walkDecls((decl) => {
        values.set(decl.prop, decl.value);
      });
      declarations.set(rule.selector, values);
    });
    const find = (prop: string) =>
      [...declarations].filter(([, values]) => values.has(prop)).map(([selector]) => selector);

    const startRules = find("padding-inline-start");
    const endRules = find("padding-inline-end");
    expect(startRules).toHaveLength(1);
    expect(endRules).toHaveLength(1);
    for (const selector of [...startRules, ...endRules]) {
      // Icon-only controls keep DaisyUI's zero padding and fixed square size.
      expect(selector).toMatch(/\.btn-square/);
      expect(selector).toMatch(/\.btn-circle/);
      // An explicit padding utility on the button keeps priority.
      expect(selector).toMatch(/px-/);
    }
    expect(startRules[0]).toContain('[data-icon="inline-start"]');
    expect(endRules[0]).toContain('[data-icon="inline-end"]');
    expect(declarations.get(startRules[0])?.get("padding-inline-start")).toBe(
      "calc(var(--btn-p) * var(--btn-icon-padding))",
    );

    // Height is owned by DaisyUI's size classes; the rule must not shrink the hit target.
    for (const values of declarations.values()) {
      expect(values.has("height") && !values.has("width")).toBe(false);
      expect(values.has("min-height")).toBe(false);
      expect(values.has("padding-block")).toBe(false);
    }
    expect(find("gap")).toHaveLength(1);
    expect(find("translate")).toEqual([
      ".btn:not(.btn-square, .btn-circle) > svg.lucide-play[data-icon]",
    ]);
  });
});
