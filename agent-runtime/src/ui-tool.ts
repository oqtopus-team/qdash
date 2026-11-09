import type { JsonValue } from "@earendil-works/chord";
import { defineTool } from "@earendil-works/pi-durable";
import { Type } from "typebox";

// The catalog, validation and fallback text are shared with the chat, which
// validates the stored spec again before rendering it. The Dockerfile copies
// this file into the image.
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

const DESCRIPTION = [
  "Render a compact, read-only UI in the QDash chat: metric cards, tables, alerts, short text, Plotly charts and links to QDash pages.",
  "Use it to present values you already have from QDash tool results; never invent or estimate values, and say in your text answer where they came from.",
  "Keep your explanation in the text answer; the UI is for scanning numbers and status. Prefer `render_chart` for a single plot.",
  "",
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
 * call with the problems listed so the model can correct it. A valid spec and
 * its plain-text fallback go out as `details.ui`, which events.ts streams as a
 * `ui` NDJSON line, the same way `render_chart` carries `details.chart`.
 */
export const uiTool = defineTool({
  name: "render_ui",
  description: DESCRIPTION,
  parameters: Type.Object({
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
      { description: "json-render flat spec." },
    ),
  }),
  replay: "safe",
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
