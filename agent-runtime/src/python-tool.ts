import { defineTool } from "@earendil-works/pi-durable";
import { Type } from "typebox";

import type { QDashConnection } from "./auth.ts";

/**
 * Runs analysis code in QDash's Python sandbox.
 *
 * The runtime never executes the code itself: it forwards to the API, where the
 * existing sandbox applies AST validation, a module allowlist, restricted
 * builtins, and bubblewrap isolation.
 */
const ALLOWED_MODULES =
  "numpy, pandas, scipy, scipy.stats, scipy.optimize, scipy.signal, scipy.interpolate, plotly, plotly.graph_objects, plotly.express, plotly.subplots, math, statistics, json, datetime, collections, io";

type SandboxResponse = {
  output?: string | null;
  error?: string | null;
  chart?: unknown;
};

export function buildPythonTool(connection: QDashConnection) {
  return defineTool({
    name: "run_python",
    description:
      "Run Python in a sandbox for calculations, statistics, and curve fitting. " +
      `Allowed imports: ${ALLOWED_MODULES}. There is no filesystem, network, or shell access, ` +
      "so data from other tools must be written into the code literally. " +
      "Set a `result` variable to a dict with an `output` string, and optionally a `chart` " +
      "holding a Plotly spec (or a list of specs) with `data` and `layout` keys. " +
      "Execution is capped at a few seconds.",
    parameters: Type.Object({
      code: Type.String({ description: "Python source to run" }),
    }),
    replay: "safe",
    execute: async (params) => {
      const baseUrl = connection.baseUrl;
      const response = await fetch(`${baseUrl}/copilot/sandbox/python`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${connection.auth.accessToken}`,
          ...(connection.auth.projectId ? { "X-Project-Id": connection.auth.projectId } : {}),
        },
        body: JSON.stringify({ code: params.code }),
      });
      if (!response.ok) {
        throw new Error(`Python sandbox returned HTTP ${response.status}`);
      }

      const result = (await response.json()) as SandboxResponse;
      if (result.error) {
        throw new Error(result.error);
      }

      const charts = Array.isArray(result.chart)
        ? result.chart
        : result.chart
          ? [result.chart]
          : [];
      const text = result.output?.trim() || "(no output)";
      return {
        content: [
          {
            type: "text" as const,
            text: charts.length > 0 ? `${text}\n\n(chart rendered in the chat UI)` : text,
          },
        ],
        // events.ts forwards details.chart to the UI, same as render_chart.
        ...(charts.length > 0 ? { details: { chart: charts[0] } } : {}),
      };
    },
  });
}
