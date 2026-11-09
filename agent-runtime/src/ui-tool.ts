import type { JsonValue } from "@earendil-works/chord";
import { defineTool } from "@earendil-works/pi-durable";
import { Type, type Static } from "typebox";

// The catalog, validation and fallback text are shared with the chat, which
// validates the stored spec again before rendering it. The Dockerfile copies
// this file into the image. Its imports resolve from the root workspace's
// node_modules, so the root package.json declares them, not this package.
import {
  UI_BLOCK_VERSION,
  UI_COMPONENT_TYPES,
  UI_SPEC_LIMITS,
  uiCatalogPrompt,
  uiSpecToText,
  validateUiSpec,
  type UiBlockPayload,
} from "../../ui/src/lib/copilotUiSpec.ts";

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

/**
 * Accepts `spec` sent as a string holding JSON, which some models and
 * providers produce for an object argument, by parsing it into the object the
 * schema expects. Malformed JSON is rejected with its location rather than
 * repaired, so the model resends a correct spec. Anything other than a string
 * `spec` is returned unchanged for schema validation.
 */
export function prepareUiArguments(args: unknown): UiToolArgs {
  if (!args || typeof args !== "object" || Array.isArray(args)) return args as UiToolArgs;
  const { spec } = args as { spec?: unknown };
  if (typeof spec !== "string") return args as UiToolArgs;
  const advice = "Send `spec` as a JSON object, not a string.";
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
      `render_ui spec was sent as a string that is not valid JSON (${reason})${where ? `; ${where}` : ""}. ${advice} Each element's props and children belong inside that element, and every element inside \`elements\`.`,
    );
  }
  if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
    throw new Error(`render_ui spec string must hold a JSON object with root and elements. ${advice}`);
  }
  return { ...(args as Record<string, unknown>), spec: parsed } as UiToolArgs;
}

const UI_PARAMETERS = Type.Object({
  spec: Type.Object(
    {
      root: Type.String({ description: "Id of the top element." }),
      elements: Type.Record(
        Type.String(),
        Type.Object({
          // `{ type, enum }` rather than a literal union, for vLLM guided decoding.
          type: Type.Unsafe<string>({ type: "string", enum: [...UI_COMPONENT_TYPES] }),
          props: Type.Record(Type.String(), Type.Any(), {
            description: "The component's props, as listed in the tool description.",
          }),
          children: Type.Optional(Type.Array(Type.String())),
        }),
        { description: "Elements by id." },
      ),
    },
    { description: "json-render flat spec, as a JSON object (not a JSON-encoded string)." },
  ),
});

/** The arguments as `parameters` declares them; the harness validates them after `prepareArguments`. */
type UiToolArgs = Static<typeof UI_PARAMETERS>;

const DESCRIPTION = [
  "Render a compact, read-only UI in the QDash chat: metric cards, tables, alerts, short text, Plotly charts and links to QDash pages.",
  "Use it to present values you already have from QDash tool results; never invent or estimate values, and say in your text answer where they came from.",
  "Keep your explanation in the text answer; the UI is for scanning numbers and status. Prefer `render_chart` for a single plot.",
  "",
  "Pass `spec` as a JSON object, not as a string holding JSON.",
  "The spec is a flat map: `root` names the top element, and `elements` maps ids to `{ type, props, children }`.",
  "`children` lists element ids and is allowed only on Stack and Card; every other element is a leaf. Each element has exactly one parent.",
  "Only literal values: no state, visibility, repeat, watch, actions, or `$` expressions. No HTML, no Markdown, no external URLs.",
  `Limits: ${UI_SPEC_LIMITS.maxElements} elements, depth ${UI_SPEC_LIMITS.maxDepth}, ${UI_SPEC_LIMITS.maxChildren} children per element, ${UI_SPEC_LIMITS.maxTableRows} table rows, ${UI_SPEC_LIMITS.maxTableColumns} columns, ${UI_SPEC_LIMITS.maxBytes} characters in all.`,
  "",
  "Components:",
  uiCatalogPrompt(),
  "",
  'Example: {"root":"s","elements":{"s":{"type":"Stack","props":{"direction":"horizontal"},"children":["t1","f"]},"t1":{"type":"Metric","props":{"label":"T1","value":42.1,"unit":"us","detail":"Q03"},"children":[]},"f":{"type":"Metric","props":{"label":"X90 fidelity","value":0.9971,"tone":"success"},"children":[]}}}',
].join("\n");

/**
 * Lets the model compose a read-only UI in the QDash chat.
 *
 * The spec is validated against the shared catalog; an invalid one fails the
 * call with the problems listed so the model can correct it. A spec sent as a
 * JSON string is parsed first (`prepareUiArguments`) and then checked the same
 * way as an object; malformed JSON fails with its location. A valid spec and
 * its plain-text fallback go out as `details.ui`, which events.ts streams as a
 * `ui` NDJSON line, the same way `render_chart` carries `details.chart`.
 */
export const uiTool = defineTool({
  name: "render_ui",
  description: DESCRIPTION,
  parameters: UI_PARAMETERS,
  replay: "safe",
  prepareArguments: prepareUiArguments,
  execute: async (params) => {
    const result = validateUiSpec(params.spec);
    if (!result.ok) {
      throw new Error(`render_ui spec is invalid:\n- ${result.errors.slice(0, 12).join("\n- ")}`);
    }
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
