import { defineTool } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

/**
 * Lets the model render a Plotly chart in the QDash chat UI.
 *
 * The spec is passed through untouched; `details.chart` is picked up by
 * events.ts and streamed as a `chart` NDJSON line.
 */
export const chartTool = defineTool({
  name: "render_chart",
  label: "Render chart",
  description:
    "Render a Plotly chart in the QDash chat UI. Provide Plotly traces in `data` and an optional `layout`. Use this instead of describing a plot in text when the user asks to visualize data.",
  parameters: Type.Object({
    data: Type.Array(Type.Any(), { description: "Plotly traces" }),
    layout: Type.Optional(Type.Any({ description: "Plotly layout" })),
  }),
  execute: async (_toolCallId, params) => ({
    content: [{ type: "text" as const, text: "Chart rendered in the chat UI." }],
    details: { chart: { data: params.data, layout: params.layout ?? {} } },
  }),
});
