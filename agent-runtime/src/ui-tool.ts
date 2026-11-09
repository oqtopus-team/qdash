import type { JsonValue } from "@earendil-works/chord";
import { defineTool } from "@earendil-works/pi-durable";

// The catalog, validation and fallback text are shared with the chat, which
// validates the stored spec again before rendering it. The Dockerfile copies
// this file into the image. Its imports resolve from the root workspace's
// node_modules, so the root package.json declares them, not this package.
import {
  UI_BLOCK_VERSION,
  UI_SPEC_LIMITS,
  uiCatalogPrompt,
  uiSpecToText,
  validateUiSpec,
  type UiBlockPayload,
} from "../../ui/src/lib/copilotUiSpec.ts";
import {
  UI_INPUT_GROUPS,
  UI_TOOL_PARAMETERS,
  specFromToolArgs,
  toolArgsFromSpec,
  type UiToolArgs,
} from "./ui-tool-input.ts";

export {
  UI_BLOCK_VERSION,
  UI_SPEC_LIMITS,
  validateUiSpec,
  type UiBlockPayload,
} from "../../ui/src/lib/copilotUiSpec.ts";

/** A `ui` block read back from tool details, re-validated so replayed entries are checked too. */
export function uiBlockFromDetails(details: unknown): UiBlockPayload | undefined {
  if (!details || typeof details !== "object" || !("ui" in details)) return undefined;
  const ui = (details as { ui?: unknown }).ui;
  if (!ui || typeof ui !== "object") return undefined;
  const { version, spec, fallback } = ui as Record<string, unknown>;
  if (version !== UI_BLOCK_VERSION || typeof fallback !== "string") return undefined;
  const result = validateUiSpec(spec);
  return result.ok ? { version, spec: result.spec, fallback } : undefined;
}

/** Longest JSON-encoded `spec` string that is parsed; whitespace may make it longer than the compact limit. */
const MAX_SPEC_STRING_LENGTH = UI_SPEC_LIMITS.maxBytes * 2;
const SNIPPET_RADIUS = 40;

/** The text around `index`, with `⟨here⟩` marking the position. */
function snippetAt(text: string, index: number): string {
  const start = Math.max(0, index - SNIPPET_RADIUS);
  const end = Math.min(text.length, index + SNIPPET_RADIUS);
  return `${start > 0 ? "…" : ""}${text.slice(start, index)}⟨here⟩${text.slice(index, end)}${end < text.length ? "…" : ""}`;
}

/**
 * Where the brackets of a JSON text stop balancing, if they do: a closer with
 * no opener or of the wrong kind, text after the top-level value ends, or an
 * unterminated string or bracket. Only locates the problem; never repairs it.
 */
function locateBracketProblem(text: string): string | undefined {
  const open: string[] = [];
  let inString = false;
  let escaped = false;
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    if (inString) {
      if (escaped) escaped = false;
      else if (ch === "\\") escaped = true;
      else if (ch === '"') inString = false;
      continue;
    }
    if (ch === '"') inString = true;
    else if (ch === "{" || ch === "[") open.push(ch === "{" ? "}" : "]");
    else if (ch === "}" || ch === "]") {
      const expected = open.pop();
      if (expected === undefined) {
        return `unmatched "${ch}" at character ${i}: ${snippetAt(text, i)}`;
      }
      if (ch !== expected) {
        return `"${ch}" at character ${i} where "${expected}" was expected: ${snippetAt(text, i)}`;
      }
      if (open.length === 0) {
        const rest = text.slice(i + 1).search(/\S/);
        if (rest === -1) return undefined;
        const at = i + 1 + rest;
        return `the top-level object closes at character ${i} but text continues at character ${at}, so a "}" or "]" before it is likely extra and closed an element or \`elements\` early: ${snippetAt(text, at)}`;
      }
    }
  }
  if (inString) return "a string is not terminated";
  if (open.length > 0) return `${open.length} bracket(s) are not closed; expected "${open.reverse().join("")}" at the end`;
  return undefined;
}

/** The earlier `{ spec }` form's spec, parsed when it was sent as a JSON string. */
function parseSpecString(spec: string): unknown {
  const advice = "Send the elements as JSON objects, not as a string.";
  if (spec.length > MAX_SPEC_STRING_LENGTH) {
    throw new Error(
      `render_ui spec is a ${spec.length}-character string; the limit is ${UI_SPEC_LIMITS.maxBytes} characters of compact JSON. ${advice}`,
    );
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(spec);
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    const where = locateBracketProblem(spec);
    throw new Error(
      `render_ui spec was sent as a string that is not valid JSON (${reason})${where ? `; ${where}` : ""}. ${advice} Each element's fields belong inside that element.`,
    );
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`render_ui spec string must hold a JSON object with root and elements. ${advice}`);
  }
  return parsed;
}

/** An element list sent as a JSON string, parsed; malformed JSON is rejected with its location. */
function parseGroupString(group: string, text: string): unknown {
  const advice = `Send \`${group}\` as a JSON array, not a string.`;
  if (text.length > MAX_SPEC_STRING_LENGTH) {
    throw new Error(`render_ui ${group} is a ${text.length}-character string. ${advice}`);
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    const where = locateBracketProblem(text);
    throw new Error(
      `render_ui ${group} was sent as a string that is not valid JSON (${reason})${where ? `; ${where}` : ""}. ${advice}`,
    );
  }
  if (!Array.isArray(parsed)) throw new Error(`render_ui ${group} string must hold a JSON array. ${advice}`);
  return parsed;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** One element in a form models often send instead of the declared one, rewritten; anything else unchanged. */
function prepareElement(group: string, item: unknown): unknown {
  if (!isRecord(item)) return item;
  if (group === "tables" && Array.isArray(item.rows) && Array.isArray(item.columns)) {
    const keys = item.columns.map((column) => (isRecord(column) ? column.key : undefined));
    // Rows keyed by column, as the stored spec keeps them, become cell lists.
    const rows = item.rows.map((row) =>
      isRecord(row) ? keys.map((key) => (typeof key === "string" && Object.hasOwn(row, key) ? row[key] : null)) : row,
    );
    return { ...item, rows };
  }
  if (group === "charts") {
    // Traces and layout sent as JSON values rather than text.
    const data = Array.isArray(item.data) ? JSON.stringify(item.data) : item.data;
    const layout = isRecord(item.layout) ? JSON.stringify(item.layout) : item.layout;
    return { ...item, data, ...(layout === undefined ? {} : { layout }) };
  }
  return item;
}

/**
 * Brings arguments into the declared form before schema validation. Models
 * without constrained sampling sometimes send a JSON value as a string, or
 * leave out element lists they do not use; providers that sample against
 * the schema never do. Malformed JSON is rejected with its location rather
 * than repaired, so the model resends a correct call.
 *
 * Calls in the earlier `{ spec }` form (a json-render spec, or a string
 * holding one), as recorded in existing sessions, are validated against the
 * catalog and rewritten into the declared form. Never mutates `args`.
 */
export function prepareUiArguments(args: unknown): UiToolArgs {
  if (!isRecord(args)) return args as UiToolArgs;
  if ("spec" in args) {
    const spec = typeof args.spec === "string" ? parseSpecString(args.spec) : args.spec;
    const result = validateUiSpec(spec);
    if (!result.ok) throw invalidSpecError(result.errors);
    return toolArgsFromSpec(result.spec);
  }
  const prepared: Record<string, unknown> = { ...args };
  for (const group of Object.values(UI_INPUT_GROUPS)) {
    let items = prepared[group];
    if (items === undefined || items === null) items = [];
    if (typeof items === "string") items = parseGroupString(group, items);
    prepared[group] = Array.isArray(items) ? items.map((item) => prepareElement(group, item)) : items;
  }
  return prepared as UiToolArgs;
}

function invalidSpecError(errors: string[]): Error {
  return new Error(`render_ui spec is invalid:\n- ${errors.slice(0, 12).join("\n- ")}`);
}

const DESCRIPTION = [
  "Render a compact, read-only UI in the QDash chat: metric cards, tables, alerts, short text, Plotly charts and links to QDash pages.",
  "Use it to present values you already have from QDash tool results; never invent or estimate values, and say in your text answer where they came from.",
  "Keep your explanation in the text answer; the UI is for scanning numbers and status. Prefer `render_chart` for a single plot.",
  "",
  "List each element under its type (`stacks`, `cards`, `metrics`, `tables`, `alerts`, `texts`, `charts`, `links`) with a unique `id`; send an empty list for a type you do not use. `root` names the top element.",
  "Only Stack and Card have `children`, the ids of their child elements; every other element is a leaf. Each element has exactly one parent.",
  "A table row lists one cell per column, in column order. A chart's `data` and `layout` are JSON text.",
  "Only literal values: no state, visibility, repeat, watch, actions, or `$` expressions. No HTML, no Markdown, no external URLs.",
  `Limits: ${UI_SPEC_LIMITS.maxElements} elements, depth ${UI_SPEC_LIMITS.maxDepth}, ${UI_SPEC_LIMITS.maxChildren} children per element, ${UI_SPEC_LIMITS.maxTableRows} table rows, ${UI_SPEC_LIMITS.maxTableColumns} columns, ${UI_SPEC_LIMITS.maxBytes} characters in all.`,
  "",
  "Components:",
  uiCatalogPrompt(),
  "",
  'Example: {"root":"s","stacks":[{"id":"s","direction":"horizontal","children":["t1","f"]}],"cards":[],"metrics":[{"id":"t1","label":"T1","value":42.1,"unit":"us","detail":"Q03"},{"id":"f","label":"X90 fidelity","value":0.9971,"tone":"success"}],"tables":[],"alerts":[],"texts":[],"charts":[],"links":[]}',
].join("\n");

/**
 * Lets the model compose a read-only UI in the QDash chat.
 *
 * The arguments list elements by component type (ui-tool-input.ts), a shape
 * strict JSON schemas can express, so the tool asks providers that support it
 * to sample its arguments against the schema. `strict: "prefer"` sends the
 * schema as a hint, unenforced, to models without that support instead of
 * failing their requests, so `prepareUiArguments` still repairs the forms
 * those models send. The arguments are then mapped to a json-render spec and
 * validated against the shared catalog; an invalid one fails the call with
 * the problems listed so the model can correct it. A valid spec and its
 * plain-text fallback go out as `details.ui`, which events.ts streams as a
 * `ui` NDJSON line, the same way `render_chart` carries `details.chart`.
 */
export const uiTool = defineTool({
  name: "render_ui",
  description: DESCRIPTION,
  parameters: UI_TOOL_PARAMETERS,
  constrainedSampling: { type: "json_schema", strict: "prefer" },
  replay: "safe",
  prepareArguments: prepareUiArguments,
  execute: async (params) => {
    const mapped = specFromToolArgs(params);
    if (!mapped.ok) throw invalidSpecError(mapped.errors);
    const result = validateUiSpec(mapped.spec);
    if (!result.ok) throw invalidSpecError(result.errors);
    const ui: UiBlockPayload = {
      version: UI_BLOCK_VERSION,
      spec: result.spec,
      fallback: uiSpecToText(result.spec),
    };
    const count = Object.keys(result.spec.elements).length;
    return {
      output: [
        {
          type: "text" as const,
          text: `UI rendered in the chat (${count} element${count === 1 ? "" : "s"}). Do not repeat its values in full; summarize what they mean.`,
        },
      ],
      details: { ui } as unknown as JsonValue,
    };
  },
});
