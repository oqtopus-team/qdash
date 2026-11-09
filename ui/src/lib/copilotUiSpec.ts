/**
 * The read-only UI the Copilot can compose in a chat answer (`render_ui`).
 *
 * One definition serves both ends: the Agent Runtime validates the model's
 * spec with it before the tool succeeds (agent-runtime/src/ui-tool.ts imports
 * this file), and the chat validates the stored spec again before rendering
 * it. Keep this module free of React and of `@/` imports so the runtime can
 * load it, and within the ES2020 library the UI compiles against.
 *
 * Specs use json-render's flat format (`root` plus an `elements` map). Only
 * `type`, `props` and `children` are accepted on an element: no state,
 * visibility, repeat, watchers, actions or `$` expressions. Every prop is
 * checked against the component's schema, and the tree is bounded in size and
 * depth and must be acyclic.
 */

import { defineCatalog, defineSchema, validateSpec, type Spec } from "@json-render/core";
import { z } from "zod";

/**
 * Version of the stored `ui` block; a reader that does not know it shows the fallback.
 * @public Also read by the Agent Runtime.
 */
export const UI_BLOCK_VERSION = 1;

/**
 * Bounds on one spec, so a single answer cannot grow the stored session without limit.
 * @public Also read by the Agent Runtime.
 */
export const UI_SPEC_LIMITS = {
  /** Serialized JSON length of the spec. */
  maxBytes: 100_000,
  maxElements: 60,
  /** Root is depth 1. */
  maxDepth: 8,
  maxChildren: 24,
  maxKeyLength: 64,
  maxTableRows: 100,
  maxTableColumns: 12,
  maxChartTraces: 12,
  /** Longest plain-text fallback kept with the block. */
  maxFallbackChars: 8_000,
} as const;

/**
 * Internal pages a `Link` may open, by first path segment. Detail pages only
 * need their ids, which the model has from tool results.
 */
const UI_LINK_PREFIXES = [
  "chip",
  "execution",
  "executions",
  "task-results",
  "tasks",
  "metrics",
  "analysis",
  "forum",
  "evaluations",
] as const;

const MAX_LINK_LENGTH = 400;
const PLACEHOLDER_ORIGIN = "https://qdash.invalid";

/**
 * The normalized path of an internal QDash page, or null for anything else:
 * absolute and protocol-relative URLs, other schemes, backslashes, control
 * characters, and paths outside `UI_LINK_PREFIXES`.
 */
export function safeInternalHref(href: unknown): string | null {
  if (typeof href !== "string" || href.length === 0 || href.length > MAX_LINK_LENGTH) return null;
  // eslint-disable-next-line no-control-regex -- rejecting control characters is the point
  if (!href.startsWith("/") || href.startsWith("//") || /[\\\u0000-\u001f\u007f]/.test(href)) {
    return null;
  }
  let url: URL;
  try {
    url = new URL(href, PLACEHOLDER_ORIGIN);
  } catch {
    return null;
  }
  if (url.origin !== PLACEHOLDER_ORIGIN) return null;
  const first = url.pathname.split("/")[1] ?? "";
  if (!(UI_LINK_PREFIXES as readonly string[]).includes(first)) return null;
  return `${url.pathname}${url.search}${url.hash}`;
}

const text = (max: number) => z.string().min(1).max(max);
const tone = z.enum(["neutral", "info", "success", "warning", "error"]);
const cell = z.union([z.string().max(500), z.number(), z.boolean(), z.null()]);

// Trace types the chat's Plotly bundle draws well in a narrow column.
const traceType = z.enum(["scatter", "scattergl", "bar", "histogram", "heatmap", "box"]);

const uiSchema = defineSchema((s) => ({
  spec: s.object({
    root: s.string(),
    elements: s.record(
      s.object({
        type: s.ref("catalog.components"),
        props: s.propsOf("catalog.components"),
        children: s.array(s.string()),
      }),
    ),
  }),
  catalog: s.object({
    components: s.map({
      props: s.zod(),
      description: s.string(),
    }),
  }),
}));

export const uiCatalog = defineCatalog(uiSchema, {
  components: {
    Stack: {
      props: z
        .object({
          direction: z.enum(["vertical", "horizontal"]).optional(),
          gap: z.enum(["sm", "md", "lg"]).optional(),
        })
        .strict(),
      description:
        "Layout container. `direction` vertical (default) or horizontal; horizontal rows wrap in a narrow chat. `gap` sm, md (default) or lg.",
    },
    Card: {
      props: z
        .object({
          title: text(120).optional(),
          description: text(300).optional(),
        })
        .strict(),
      description: "Bordered group with an optional `title` and one-line `description`.",
    },
    Metric: {
      props: z
        .object({
          label: text(80),
          value: z.union([text(60), z.number()]),
          unit: text(20).optional(),
          detail: text(160).optional(),
          tone: tone.optional(),
        })
        .strict(),
      description:
        "One value with its `label`, optional `unit`, a short `detail` (qubit, execution, time) and a status `tone` (neutral default, info, success, warning, error). Leaf.",
    },
    Table: {
      props: z
        .object({
          caption: text(160).optional(),
          columns: z
            .array(
              z
                .object({
                  key: text(UI_SPEC_LIMITS.maxKeyLength),
                  label: text(60),
                  align: z.enum(["left", "right"]).optional(),
                })
                .strict(),
            )
            .min(1)
            .max(UI_SPEC_LIMITS.maxTableColumns),
          rows: z
            .array(z.record(z.string().max(UI_SPEC_LIMITS.maxKeyLength), cell))
            .max(UI_SPEC_LIMITS.maxTableRows),
        })
        .strict(),
      description:
        "Rows of values. `columns` lists `{ key, label, align? }` (right-align numbers); each row maps column keys to a string, number, boolean or null. Leaf.",
    },
    Alert: {
      props: z
        .object({
          tone: z.enum(["info", "success", "warning", "error"]),
          title: text(120).optional(),
          message: text(1_000),
        })
        .strict(),
      description: "A status message with `tone` info, success, warning or error. Leaf.",
    },
    Text: {
      props: z
        .object({
          text: text(2_000),
          variant: z.enum(["body", "muted", "heading"]).optional(),
        })
        .strict(),
      description: "Plain text (no Markdown). `variant` body (default), muted or heading. Leaf.",
    },
    Chart: {
      props: z
        .object({
          data: z
            .array(z.object({ type: traceType.optional() }).loose())
            .min(1)
            .max(UI_SPEC_LIMITS.maxChartTraces),
          layout: z.record(z.string(), z.unknown()).optional(),
        })
        .strict(),
      description:
        "A Plotly chart: `data` traces (type scatter, scattergl, bar, histogram, heatmap or box) and an optional `layout`. Leaf.",
    },
    Link: {
      props: z
        .object({
          label: text(120),
          href: z.string().refine((href) => safeInternalHref(href) !== null, {
            message: `must be a QDash path starting with /${UI_LINK_PREFIXES.join(", /")}`,
          }),
        })
        .strict(),
      description:
        "A link to a QDash page, such as /chip/{chipId}/qubit/{qid}, /execution/{chipId}/{executionId}, /executions/{executionId} or /task-results/{taskId}. Leaf.",
    },
  },
});

type UiComponentType = keyof typeof uiCatalog.data.components;
/** @public Also read by the Agent Runtime. */
export const UI_COMPONENT_TYPES = Object.keys(uiCatalog.data.components) as UiComponentType[];
const CONTAINER_TYPES: ReadonlySet<string> = new Set(["Stack", "Card"]);

interface UiElement {
  type: UiComponentType;
  props: Record<string, unknown>;
  children: string[];
}

export interface UiSpec {
  root: string;
  elements: Record<string, UiElement>;
}

/** What `render_ui` produces and the chat stores as a `ui` block. */
export interface UiBlockPayload {
  version: number;
  spec: UiSpec;
  /** The same content as plain text, for copying, forum replies and readers that cannot render it. */
  fallback: string;
}

export type UiSpecValidation = { ok: true; spec: UiSpec } | { ok: false; errors: string[] };

const KEY_PATTERN = /^[A-Za-z0-9_-]+$/;
const ELEMENT_FIELDS = new Set(["type", "props", "children"]);

function isPlainObject(value: unknown): value is Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

function hasOwn(object: object, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(object, key);
}

/** Path of the first `$`-prefixed key (a json-render expression) inside a value. */
function findExpression(value: unknown, path: string): string | null {
  if (Array.isArray(value)) {
    for (let i = 0; i < value.length; i++) {
      const found = findExpression(value[i], `${path}[${i}]`);
      if (found) return found;
    }
  } else if (value !== null && typeof value === "object") {
    for (const key of Object.keys(value)) {
      if (key.startsWith("$")) return `${path}.${key}`;
      const found = findExpression((value as Record<string, unknown>)[key], `${path}.${key}`);
      if (found) return found;
    }
  }
  return null;
}

function formatZodIssues(error: z.ZodError): string {
  return error.issues
    .slice(0, 3)
    .map((issue) => `${issue.path.length ? `${issue.path.join(".")}: ` : ""}${issue.message}`)
    .join("; ");
}

/**
 * Validate a spec as the model or a stored message gave it.
 *
 * Returns the normalized spec (props as parsed, missing `children` as `[]`)
 * or every problem found, phrased so the model can correct its call.
 */
export function validateUiSpec(input: unknown): UiSpecValidation {
  let size: number;
  try {
    size = JSON.stringify(input)?.length ?? 0;
  } catch {
    return { ok: false, errors: ["spec is not serializable JSON (it may contain a cycle)"] };
  }
  if (size > UI_SPEC_LIMITS.maxBytes) {
    return {
      ok: false,
      errors: [`spec is ${size} characters; the limit is ${UI_SPEC_LIMITS.maxBytes}`],
    };
  }
  if (!isPlainObject(input)) return { ok: false, errors: ["spec must be an object"] };

  const errors: string[] = [];
  for (const key of Object.keys(input)) {
    if (key !== "root" && key !== "elements") {
      errors.push(`spec.${key} is not supported; a spec has only root and elements`);
    }
  }
  const { root, elements } = input;
  if (typeof root !== "string" || !root) errors.push("spec.root must name an element");
  if (!isPlainObject(elements)) {
    errors.push("spec.elements must be an object keyed by element id");
    return { ok: false, errors };
  }
  const keys = Object.keys(elements);
  if (keys.length === 0) errors.push("spec.elements is empty");
  if (keys.length > UI_SPEC_LIMITS.maxElements) {
    errors.push(`spec has ${keys.length} elements; the limit is ${UI_SPEC_LIMITS.maxElements}`);
    return { ok: false, errors };
  }

  const normalized: Record<string, UiElement> = {};
  for (const key of keys) {
    const where = `elements.${key}`;
    if (key.length > UI_SPEC_LIMITS.maxKeyLength || !KEY_PATTERN.test(key)) {
      errors.push(`${where}: element ids use letters, digits, - and _ only`);
      continue;
    }
    const element = elements[key];
    if (!isPlainObject(element)) {
      errors.push(`${where} must be an object`);
      continue;
    }
    for (const field of Object.keys(element)) {
      if (!ELEMENT_FIELDS.has(field)) {
        errors.push(`${where}.${field} is not supported; use only type, props and children`);
      }
    }
    const { type } = element;
    if (typeof type !== "string" || !hasOwn(uiCatalog.data.components, type)) {
      errors.push(`${where}.type must be one of ${UI_COMPONENT_TYPES.join(", ")}`);
      continue;
    }
    const children = element.children ?? [];
    if (!Array.isArray(children) || children.some((child) => typeof child !== "string")) {
      errors.push(`${where}.children must be an array of element ids`);
      continue;
    }
    if (children.length > 0 && !CONTAINER_TYPES.has(type)) {
      errors.push(`${where}: ${type} cannot have children; only Stack and Card can`);
    }
    if (children.length > UI_SPEC_LIMITS.maxChildren) {
      errors.push(
        `${where} has ${children.length} children; the limit is ${UI_SPEC_LIMITS.maxChildren}`,
      );
    }
    if (new Set(children).size !== children.length) {
      errors.push(`${where}.children lists an element twice`);
    }
    const props = element.props ?? {};
    const expression = findExpression(props, `${where}.props`);
    if (expression) {
      errors.push(`${expression}: expressions are not supported; give literal values`);
      continue;
    }
    const definition = uiCatalog.data.components[type as UiComponentType];
    const parsed = definition.props.safeParse(props);
    if (!parsed.success) {
      errors.push(`${where} (${type}) props: ${formatZodIssues(parsed.error)}`);
      continue;
    }
    normalized[key] = {
      type: type as UiComponentType,
      props: parsed.data as Record<string, unknown>,
      children: children as string[],
    };
  }
  if (errors.length > 0) return { ok: false, errors };

  const spec: UiSpec = { root: root as string, elements: normalized };
  // json-render's own structural check: root present, children resolve.
  const structure = validateSpec(spec as unknown as Spec, { checkOrphans: true });
  for (const issue of structure.issues) {
    if (issue.severity === "error" || issue.code === "orphaned_element") {
      errors.push(issue.message);
    }
  }
  if (errors.length > 0) return { ok: false, errors };

  // A tree: no cycles, no element under two parents, bounded depth.
  const seen = new Set<string>();
  const walk = (key: string, depth: number, path: ReadonlySet<string>): void => {
    if (path.has(key)) {
      errors.push(`elements.${key} contains itself (cycle)`);
      return;
    }
    if (seen.has(key)) {
      errors.push(`elements.${key} has more than one parent`);
      return;
    }
    seen.add(key);
    if (depth > UI_SPEC_LIMITS.maxDepth) {
      errors.push(`the tree is deeper than ${UI_SPEC_LIMITS.maxDepth} levels at elements.${key}`);
      return;
    }
    const next = new Set(path).add(key);
    for (const child of spec.elements[key].children) {
      walk(child, depth + 1, next);
      if (errors.length > 0) return;
    }
  };
  walk(spec.root, 1, new Set());
  if (errors.length > 0) return { ok: false, errors };

  // The catalog's own spec schema, as json-render defines it.
  const checked = uiCatalog.validate(spec);
  if (!checked.success) {
    return {
      ok: false,
      errors: [checked.error ? formatZodIssues(checked.error) : "spec is invalid"],
    };
  }
  return { ok: true, spec };
}

function chartTitle(layout: Record<string, unknown> | undefined): string | null {
  const title = layout?.title;
  if (typeof title === "string") return title;
  if (isPlainObject(title) && typeof title.text === "string") return title.text;
  return null;
}

function cellText(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/\|/g, "\\|")
    .replace(/\s*\n\s*/g, " ");
}

/**
 * The spec as plain Markdown-compatible text: headings, `label: value`
 * lines, Markdown tables and link paths. Charts are named, not described.
 */
export function uiSpecToText(spec: UiSpec): string {
  const lines: string[] = [];
  const visit = (key: string) => {
    const element = spec.elements[key];
    if (!element) return;
    const p = element.props;
    switch (element.type) {
      case "Card":
        if (typeof p.title === "string") lines.push(`### ${p.title}`);
        if (typeof p.description === "string") lines.push(p.description);
        break;
      case "Metric": {
        const unit = typeof p.unit === "string" ? ` ${p.unit}` : "";
        const detail = typeof p.detail === "string" ? ` (${p.detail})` : "";
        lines.push(`- ${String(p.label)}: ${String(p.value)}${unit}${detail}`);
        break;
      }
      case "Table": {
        const columns = p.columns as { key: string; label: string; align?: string }[];
        const rows = p.rows as Record<string, unknown>[];
        if (typeof p.caption === "string") lines.push(p.caption);
        lines.push(
          [
            `| ${columns.map((c) => cellText(c.label)).join(" | ")} |`,
            `| ${columns.map((c) => (c.align === "right" ? "---:" : "---")).join(" | ")} |`,
            ...rows.map((row) => `| ${columns.map((c) => cellText(row[c.key])).join(" | ")} |`),
          ].join("\n"),
        );
        break;
      }
      case "Alert": {
        const title = typeof p.title === "string" ? `${p.title}: ` : "";
        lines.push(`> **${String(p.tone).toUpperCase()}** ${title}${String(p.message)}`);
        break;
      }
      case "Text":
        lines.push(p.variant === "heading" ? `### ${String(p.text)}` : String(p.text));
        break;
      case "Chart":
        lines.push(`[Chart: ${chartTitle(p.layout as Record<string, unknown>) ?? "untitled"}]`);
        break;
      case "Link":
        lines.push(`${String(p.label)}: ${String(p.href)}`);
        break;
      default:
        break;
    }
    for (const child of element.children) visit(child);
  };
  visit(spec.root);
  const out = lines.join("\n\n");
  return out.length > UI_SPEC_LIMITS.maxFallbackChars
    ? `${out.slice(0, UI_SPEC_LIMITS.maxFallbackChars)}…`
    : out;
}

/**
 * Read a stored or streamed `ui` block. A block whose version this build
 * does not know, or whose spec does not validate, keeps only its fallback.
 */
export function parseUiBlock(
  value: unknown,
): { status: "ok"; spec: UiSpec; fallback: string } | { status: "fallback"; fallback: string } {
  if (!isPlainObject(value)) return { status: "fallback", fallback: "" };
  const fallback = typeof value.fallback === "string" ? value.fallback : "";
  if (value.version !== UI_BLOCK_VERSION) return { status: "fallback", fallback };
  const result = validateUiSpec(value.spec);
  return result.ok
    ? { status: "ok", spec: result.spec, fallback }
    : { status: "fallback", fallback };
}

/**
 * Component reference for the model, from the catalog's own descriptions.
 * @public Used by the Agent Runtime's `render_ui` tool.
 */
export function uiCatalogPrompt(): string {
  return UI_COMPONENT_TYPES.map(
    (type) => `- ${type}: ${uiCatalog.data.components[type].description}`,
  ).join("\n");
}
