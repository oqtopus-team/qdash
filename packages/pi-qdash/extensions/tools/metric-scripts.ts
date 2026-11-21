import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import type { QDashClient } from "@oqtopus-team/qdash-client";
import { QDash, Script } from "@oqtopus-team/qdash-sdk";
import { Type } from "typebox";

import { dashboardPagePath, metricScriptPagePath } from "../lib/links.js";
import { toTextToolResult } from "../lib/results.js";

/**
 * Metric scripts and dashboards.
 *
 * A metric script is Python written against the `qdash_metrics` API; QDash runs
 * it in a bounded worker process and turns it into one value per qubit or
 * directed pair. Validation and previews execute the code on the server but
 * persist nothing, so they are direct tools rather than script-callable reads;
 * saving a script or a dashboard is a confirmation-gated write. Scripts are
 * saved through the SDK's `qdash.scripts`; dashboards keep the client's partial
 * update, which the SDK's whole-definition save does not express. These tools
 * only reach the API and format its answers; how to write a script and read
 * its results lives in the qdash-metric-scripts skill.
 */

type ConnectionParams = { profile?: string; configPath?: string; useEnv?: boolean };

/** The slice of QDashClient these tools use; tests pass a stub. */
export type MetricScriptClient = Pick<
  QDashClient,
  | "listMetricScripts"
  | "getMetricScript"
  | "listMetricScriptTemplates"
  | "getMetricScriptCatalog"
  | "validateMetricScript"
  | "evaluateMetricScriptDraft"
  | "evaluateMetricScript"
  | "createMetricScript"
  | "updateMetricScript"
  | "listDashboards"
  | "getDashboard"
  | "listDashboardTemplates"
  | "createDashboard"
  | "updateDashboard"
>;

export type MetricScriptDependencies = {
  makeClient(params: ConnectionParams): Promise<MetricScriptClient>;
  /** The chip to evaluate on: the explicit id, else the session/default chip. */
  resolveChipId(client: MetricScriptClient, chipId?: string): Promise<string>;
  /** The QDash web URL of a page path, when the web URL is known. */
  pageUrl?(client: MetricScriptClient, path: string): string | undefined;
};

// ---------------------------------------------------------------------------
// Response shapes (the fields formatting reads; the full response stays in details.data)
// ---------------------------------------------------------------------------

export type Diagnostic = { message: string; line?: number | null; column?: number | null; function?: string | null };

type ParameterInfo = {
  default: unknown;
  label?: string;
  kind: string;
  min?: number | null;
  max?: number | null;
  unit?: string;
  choices?: string[] | null;
};

export type MetricInfo = {
  id: string;
  title: string;
  unit: string;
  target: string;
  hops?: number[];
  parameters?: Record<string, ParameterInfo>;
  has_legend?: boolean;
};

type Cell = {
  key: string;
  status: string;
  value?: number | null;
  label?: string | null;
  message?: string | null;
  diagnostic?: Diagnostic | null;
  assessment?: { count?: number | null } | null;
};

export type EvaluateResponse = {
  script_id: string | null;
  revision: number | null;
  metric: MetricInfo;
  chip_id: string;
  start: string;
  end: string;
  params: Record<string, unknown>;
  legend: { kind: string; items?: Array<{ color: string; label: string }>; stops?: Array<{ value: number; color: string }> } | null;
  cells: Cell[];
  log?: string;
  evaluated_at: string;
  truncated?: boolean;
};

type ValidateResponse = { ok: boolean; metrics: MetricInfo[]; diagnostics: Diagnostic[] };

type ScriptResponse = {
  script_id: string;
  name: string;
  visibility: string;
  status: string;
  revision: number;
  active_revision: number | null;
  metrics: MetricInfo[];
  diagnostics: Diagnostic[];
};

type DashboardPanel = {
  panel_id?: string;
  type?: string;
  title?: string;
  config?: Record<string, unknown>;
  script_name?: string | null;
  latest_revision?: number | null;
};

type DashboardResponse = {
  dashboard_id: string;
  name: string;
  visibility: string;
  chip_id: string | null;
  panels: DashboardPanel[];
};

// ---------------------------------------------------------------------------
// qdash_query actions
// ---------------------------------------------------------------------------

export const METRIC_SCRIPT_QUERY_ACTIONS = [
  "metric_scripts",
  "metric_script",
  "metric_script_templates",
  "metric_script_template",
  "metric_script_catalog",
  "dashboards",
  "dashboard",
  "dashboard_templates",
] as const;

export type MetricScriptQueryAction = (typeof METRIC_SCRIPT_QUERY_ACTIONS)[number];

export function isMetricScriptQueryAction(action: string): action is MetricScriptQueryAction {
  return (METRIC_SCRIPT_QUERY_ACTIONS as readonly string[]).includes(action);
}

function required(value: string | undefined, name: string): string {
  if (!value) throw new Error(`${name} is required for this action`);
  return value;
}

/** The read-only metric script and dashboard actions of `qdash_query`. */
export async function metricScriptQuery(
  client: MetricScriptClient,
  action: MetricScriptQueryAction,
  params: { scriptId?: string; templateId?: string; dashboardId?: string },
): Promise<unknown> {
  switch (action) {
    case "metric_scripts":
      return client.listMetricScripts();
    case "metric_script":
      return client.getMetricScript(required(params.scriptId, "scriptId"));
    case "metric_script_templates": {
      // The list without sources; metric_script_template returns one with its source.
      const { templates } = await client.listMetricScriptTemplates();
      return { templates: templates.map(({ source: _source, ...rest }) => rest) };
    }
    case "metric_script_template": {
      const templateId = required(params.templateId, "templateId");
      const { templates } = await client.listMetricScriptTemplates();
      const template = templates.find((item) => item.template_id === templateId);
      if (!template) {
        throw new Error(`Unknown metric script template '${templateId}'; available: ${templates.map((item) => item.template_id).join(", ")}`);
      }
      return template;
    }
    case "metric_script_catalog":
      return client.getMetricScriptCatalog();
    case "dashboards":
      return client.listDashboards();
    case "dashboard":
      return client.getDashboard(required(params.dashboardId, "dashboardId"));
    case "dashboard_templates":
      return client.listDashboardTemplates();
  }
}

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------

function formatValue(value: number): string {
  if (value === 0) return "0";
  const magnitude = Math.abs(value);
  if (magnitude >= 1e5 || magnitude < 1e-3) return value.toExponential(3);
  return String(Number(value.toPrecision(5)));
}

export function formatDiagnostic(diagnostic: Diagnostic): string {
  const where: string[] = [];
  if (typeof diagnostic.line === "number") where.push(`line ${diagnostic.line}${typeof diagnostic.column === "number" ? `:${diagnostic.column}` : ""}`);
  if (diagnostic.function) where.push(`in ${diagnostic.function}`);
  return where.length ? `${where.join(" ")}: ${diagnostic.message}` : diagnostic.message;
}

function formatParameter(name: string, info: ParameterInfo): string {
  const bounds = [
    info.min !== null && info.min !== undefined ? `min ${info.min}` : "",
    info.max !== null && info.max !== undefined ? `max ${info.max}` : "",
    info.choices?.length ? `one of ${info.choices.join("|")}` : "",
  ].filter(Boolean);
  return `${name}=${JSON.stringify(info.default)} (${info.kind}${info.unit ? `, ${info.unit}` : ""}${bounds.length ? `, ${bounds.join(", ")}` : ""})`;
}

export function formatMetricInfo(metric: MetricInfo): string {
  const target = metric.target === "pair" ? `pair, hops ${(metric.hops ?? [1, 2]).join(",")}` : "qubit";
  const parameters = Object.entries(metric.parameters ?? {}).map(([name, info]) => formatParameter(name, info));
  return [
    `\`${metric.id}\` — ${metric.title} [${metric.unit}], ${target}`,
    parameters.length ? `; parameters: ${parameters.join("; ")}` : "",
    metric.has_legend ? "; has a legend" : "",
  ].join("");
}

function formatLegend(legend: EvaluateResponse["legend"], unit: string): string | undefined {
  if (!legend) return undefined;
  if (legend.kind === "continuous") {
    return `continuous: ${(legend.stops ?? []).map((stop) => `${formatValue(stop.value)} ${unit} ${stop.color}`).join(" → ")}`;
  }
  return `categorical: ${(legend.items ?? []).map((item) => `${item.color} ${item.label}`).join("; ")}`;
}

function formatCell(cell: Cell, unit: string): string {
  const count = cell.assessment?.count;
  const value = cell.status === "ok" && typeof cell.value === "number" ? `${formatValue(cell.value)} ${unit}` : cell.status;
  const notes = [cell.label, cell.status !== "ok" ? cell.message : undefined, typeof count === "number" ? `n=${count}` : undefined]
    .filter((note): note is string => typeof note === "string" && note.length > 0);
  return `- ${cell.key}: ${value}${notes.length ? ` — ${notes.join("; ")}` : ""}`;
}

const SAMPLE_CELLS = 12;
const ERROR_CELLS = 5;
const LOG_TAIL_CHARS = 1_500;

/** A summary of an evaluation; the full response goes to details.data. */
export function formatEvaluation(result: EvaluateResponse): string {
  const { metric } = result;
  const unit = metric.unit;
  const counts: Record<string, number> = { ok: 0, missing: 0, empty: 0, error: 0 };
  for (const cell of result.cells) counts[cell.status] = (counts[cell.status] ?? 0) + 1;
  const source = result.script_id ? `script ${result.script_id} revision ${result.revision}` : "draft source (not saved)";
  const params = Object.entries(result.params ?? {}).map(([key, value]) => `${key}=${JSON.stringify(value)}`);
  const lines = [
    `${metric.title} (\`${metric.id}\`) [${unit}], ${metric.target === "pair" ? `pair, hops ${(metric.hops ?? [1, 2]).join(",")}` : "qubit"}; ${source}.`,
    `Chip ${result.chip_id}, period ${result.start} → ${result.end} (evaluated ${result.evaluated_at}).`,
    ...(params.length ? [`Parameters: ${params.join(", ")}`] : []),
    `Cells: ${result.cells.length} (ok ${counts.ok}, missing ${counts.missing}, empty ${counts.empty}, error ${counts.error}).`,
  ];
  const legend = formatLegend(result.legend, unit);
  if (legend) lines.push(`Legend: ${legend}`);

  const ok = result.cells.filter((cell) => cell.status === "ok");
  const notEvaluated = result.cells.filter((cell) => cell.status === "missing" || cell.status === "empty");
  const samples = [...ok.slice(0, SAMPLE_CELLS), ...notEvaluated].slice(0, SAMPLE_CELLS);
  if (samples.length) lines.push("", `Sample cells (${samples.length} of ${result.cells.length}):`, ...samples.map((cell) => formatCell(cell, unit)));

  const errors = result.cells.filter((cell) => cell.status === "error");
  if (errors.length) {
    lines.push("", `Errors (${errors.length} cell${errors.length === 1 ? "" : "s"}${errors.length > ERROR_CELLS ? `, first ${ERROR_CELLS}` : ""}):`);
    for (const cell of errors.slice(0, ERROR_CELLS)) {
      lines.push(`- ${cell.key}: ${cell.diagnostic ? formatDiagnostic(cell.diagnostic) : (cell.message ?? "error")}`);
    }
  }
  if (result.truncated) lines.push("", "Truncated: the script log was cut, or a history() span was clamped to the broker's 400-day cap.");
  const log = (result.log ?? "").trimEnd();
  if (log) {
    const tail = log.length > LOG_TAIL_CHARS ? `…${log.slice(-LOG_TAIL_CHARS)}` : log;
    lines.push("", "Script output:", tail);
  }
  return lines.join("\n");
}

export function formatValidation(result: ValidateResponse): string {
  if (result.ok) {
    return [
      `Valid: ${result.metrics.length} metric${result.metrics.length === 1 ? "" : "s"}. Nothing was saved.`,
      ...result.metrics.map((metric) => `- ${formatMetricInfo(metric)}`),
    ].join("\n");
  }
  return [
    `Invalid (${result.diagnostics.length} problem${result.diagnostics.length === 1 ? "" : "s"}). Nothing was saved.`,
    ...result.diagnostics.map((diagnostic) => `- ${formatDiagnostic(diagnostic)}`),
  ].join("\n");
}

/** QDash's error detail as text: a string, `{message, diagnostics, log}`, or FastAPI's field errors. */
export function formatErrorDetail(detail: unknown): string | undefined {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const items = detail.map((item) => {
      if (!item || typeof item !== "object") return String(item);
      const { loc, msg } = item as { loc?: unknown; msg?: unknown };
      const where = Array.isArray(loc) ? loc.filter((part) => part !== "body").join(".") : "";
      return `${where ? `${where}: ` : ""}${typeof msg === "string" ? msg : JSON.stringify(item)}`;
    });
    return items.join("\n");
  }
  if (detail && typeof detail === "object") {
    const { message, diagnostics, log } = detail as { message?: unknown; diagnostics?: unknown; log?: unknown };
    const lines = [typeof message === "string" ? message : JSON.stringify(detail)];
    if (Array.isArray(diagnostics)) {
      for (const diagnostic of diagnostics) {
        if (diagnostic && typeof diagnostic === "object" && typeof (diagnostic as Diagnostic).message === "string") {
          lines.push(`- ${formatDiagnostic(diagnostic as Diagnostic)}`);
        }
      }
    }
    if (typeof log === "string" && log.trim()) {
      const text = log.trimEnd();
      lines.push("Script output:", text.length > LOG_TAIL_CHARS ? `…${text.slice(-LOG_TAIL_CHARS)}` : text);
    }
    return lines.join("\n");
  }
  return undefined;
}

/** An API error as `{status, text}`, or undefined for errors that are not QDash API responses. */
export function apiError(error: unknown): { status?: number; text: string } | undefined {
  if (!error || typeof error !== "object") return undefined;
  const status = (error as { statusCode?: unknown }).statusCode;
  const payload = (error as { payload?: unknown }).payload;
  const detail = payload && typeof payload === "object" ? (payload as { detail?: unknown }).detail : payload;
  const text = formatErrorDetail(detail);
  if (typeof status !== "number" && text === undefined) return undefined;
  const fallback = (error as { message?: unknown }).message;
  return {
    ...(typeof status === "number" ? { status } : {}),
    text: text ?? (typeof fallback === "string" ? fallback : "request failed"),
  };
}

function rejection(tool: string, error: unknown, what: string, extra: Record<string, unknown> = {}) {
  const failure = apiError(error);
  if (!failure) throw error;
  let hint = "";
  if (failure.status === 429) hint = "\nThe evaluation queue is full; wait a moment and try again.";
  if (failure.status === 409) hint = "\nNothing was saved. Read the current state again before retrying.";
  return toTextToolResult(
    `QDash rejected the ${what}${failure.status ? ` (HTTP ${failure.status})` : ""}: ${failure.text}${hint}`,
    { status: failure.status ?? null, detail: failure.text },
    { tool, ok: false, status: failure.status ?? null, ...extra },
  );
}

// ---------------------------------------------------------------------------
// Local checks before a write is confirmed
// ---------------------------------------------------------------------------

const MAX_SOURCE_BYTES = 256 * 1024;
const MAX_SCRIPT_NAME = 120;

export function scriptSaveProblems(params: { name: string; source: string }): string[] {
  const problems: string[] = [];
  if (!params.name.trim()) problems.push("name must not be empty");
  if (params.name.length > MAX_SCRIPT_NAME) problems.push(`name is longer than ${MAX_SCRIPT_NAME} characters`);
  if (!params.source.trim()) problems.push("source is empty");
  if (new TextEncoder().encode(params.source).length > MAX_SOURCE_BYTES) problems.push("source is larger than 256 KiB");
  return problems;
}

const PANEL_TYPES = new Set(["qubit_metric", "coupling_metric", "metric_script", "markdown"]);

export function dashboardSaveProblems(params: {
  dashboardId?: string;
  name?: string;
  templateId?: string;
  expectedVersion?: number;
  panels?: Array<Record<string, unknown>>;
}): string[] {
  const problems: string[] = [];
  if (!params.dashboardId && !params.name?.trim()) problems.push("a new dashboard needs a name");
  if (params.dashboardId && params.templateId) problems.push("templateId applies only when creating a dashboard");
  if (!params.dashboardId && params.expectedVersion !== undefined) problems.push("expectedVersion applies only when updating a dashboard");
  for (const [index, panel] of (params.panels ?? []).entries()) {
    const label = `panels[${index}]`;
    if (typeof panel.panel_id !== "string" || !panel.panel_id) problems.push(`${label}.panel_id is required`);
    if (typeof panel.type !== "string" || !PANEL_TYPES.has(panel.type)) problems.push(`${label}.type must be one of ${[...PANEL_TYPES].join(", ")}`);
    const layout = panel.layout as Record<string, unknown> | undefined;
    if (!layout || typeof layout !== "object" || ["x", "y", "w", "h"].some((key) => typeof layout[key] !== "number")) {
      problems.push(`${label}.layout needs numeric x, y, w, h`);
    } else if ((layout.x as number) + (layout.w as number) > 12) {
      problems.push(`${label}.layout exceeds the 12-column grid (x + w > 12)`);
    }
    if (panel.type === "metric_script") {
      const config = (panel.config ?? {}) as Record<string, unknown>;
      if (typeof config.script_id !== "string" || !config.script_id) problems.push(`${label}.config.script_id is required`);
      if (typeof config.metric_id !== "string" || !config.metric_id) problems.push(`${label}.config.metric_id is required`);
      if (!Number.isInteger(config.script_revision)) problems.push(`${label}.config.script_revision must pin a saved revision (an integer)`);
    }
  }
  return problems;
}

/** Panels as the API accepts them: the response-only annotations removed. */
function requestPanels(panels: Array<Record<string, unknown>>): Array<Record<string, unknown>> {
  return panels.map(({ script_name: _name, latest_revision: _latest, ...panel }) => panel);
}

function problemResult(tool: string, problems: string[], what: string) {
  const text = [
    `The ${what} cannot be saved as it is (${problems.length} problem${problems.length === 1 ? "" : "s"}). Nothing was written and no confirmation was asked.`,
    ...problems.map((problem) => `- ${problem}`),
  ].join("\n");
  return toTextToolResult(text, { problems }, { tool, saved: false, problemCount: problems.length });
}

export function formatSavedScript(result: ScriptResponse, created: boolean, url: string | undefined): string {
  const lines = [`${created ? "Created" : "Saved"} metric script '${result.name}' (${result.script_id}) as revision ${result.revision}, ${result.visibility}.`];
  if (result.status === "valid" && result.active_revision === result.revision) {
    lines.push(`It validated: revision ${result.revision} is now the active revision.`);
  } else if (result.active_revision !== null) {
    lines.push(`It did not validate (status ${result.status}): the active revision stays ${result.active_revision}, the last one that validated.`);
  } else {
    lines.push(`It did not validate (status ${result.status}), and the script has no valid revision yet; panels cannot use it.`);
  }
  if (result.diagnostics.length) lines.push("Diagnostics:", ...result.diagnostics.map((diagnostic) => `- ${formatDiagnostic(diagnostic)}`));
  if (result.metrics.length) lines.push("Metrics of the active revision:", ...result.metrics.map((metric) => `- ${formatMetricInfo(metric)}`));
  if (url) lines.push(`Page: ${url}`);
  lines.push("Dashboard panels keep the revision they pin; update a panel's script_revision to show a new revision.");
  return lines.join("\n");
}

export function formatSavedDashboard(result: DashboardResponse, created: boolean, url: string | undefined): string {
  const lines = [
    `${created ? "Created" : "Saved"} dashboard '${result.name}' (${result.dashboard_id}), ${result.visibility}${result.chip_id ? `, chip ${result.chip_id}` : ""}, ${result.panels.length} panel${result.panels.length === 1 ? "" : "s"}.`,
  ];
  for (const panel of result.panels) {
    if (panel.type !== "metric_script") continue;
    const config = panel.config ?? {};
    const pinned = config.script_revision;
    const newer = typeof panel.latest_revision === "number" && typeof pinned === "number" && panel.latest_revision > pinned;
    lines.push(
      `- ${panel.title || panel.panel_id}: ${panel.script_name ?? config.script_id} / ${config.metric_id}, pinned to revision ${pinned}${newer ? ` (revision ${panel.latest_revision} is active)` : ""}`,
    );
  }
  if (url) lines.push(`Page: ${url}`);
  return lines.join("\n");
}

// ---------------------------------------------------------------------------
// Tools
// ---------------------------------------------------------------------------

const connectionParams = {
  profile: Type.Optional(Type.String({ description: "QDash profile name. Defaults to env when QDASH_BASE_URL is set, otherwise 'default'." })),
  configPath: Type.Optional(Type.String({ description: "Optional path to qdash config.ini." })),
  useEnv: Type.Optional(Type.Boolean({ description: "Force QDASH_* environment variables instead of a profile." })),
};

const periodSchema = Type.Union(
  [
    Type.Object({ kind: Type.Literal("relative"), days: Type.Number({ description: "The last N days (1-400), resolved when the metric is evaluated." }) }),
    Type.Object({
      kind: Type.Literal("absolute"),
      start: Type.String({ description: "ISO 8601 with a timezone, such as 2026-11-01T00:00:00+09:00." }),
      end: Type.String({ description: "ISO 8601 with a timezone." }),
    }),
  ],
  { description: "Data period. Defaults to the last 14 days." },
);

type Period = { kind: "relative"; days: number } | { kind: "absolute"; start: string; end: string };

type ParamValues = Record<string, boolean | number | string>;

export function registerMetricScriptTools(pi: Pick<ExtensionAPI, "registerTool">, deps: MetricScriptDependencies): void {
  const url = (client: MetricScriptClient, path: string) => deps.pageUrl?.(client, path);

  pi.registerTool({
    name: "qdash_validate_metric_script",
    label: "QDash Validate Metric Script",
    description:
      "Compile a metric script (Python using the qdash_metrics API) in QDash's bounded worker and return its metrics (id, title, unit, target, hops, parameters) or diagnostics with line numbers. Runs the code on the server; nothing is saved and no data is read.",
    promptSnippet: "Validate metric script source without saving it",
    promptGuidelines: [
      "Validate every metric script draft with qdash_validate_metric_script before previewing or saving it; fix the reported lines first.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      source: Type.String({ description: "The complete Python source of the metric script." }),
    }),
    async execute(_toolCallId, params: ConnectionParams & { source: string }) {
      const client = await deps.makeClient(params);
      try {
        const result = (await client.validateMetricScript(params.source)) as ValidateResponse;
        return toTextToolResult(formatValidation(result), result, {
          tool: "qdash_validate_metric_script",
          ok: result.ok,
          metricIds: result.metrics.map((metric) => metric.id),
        });
      } catch (error) {
        return rejection("qdash_validate_metric_script", error, "validation");
      }
    },
  });

  pi.registerTool({
    name: "qdash_preview_metric_script",
    label: "QDash Preview Metric Script",
    description:
      "Evaluate one metric of a metric script on a chip over a period and summarize the cells: status counts, legend, sample values with sample counts, and per-cell errors with script line numbers. Pass `source` to preview a draft, or `scriptId` (optionally `revision`) to evaluate a saved script. Executes the code on the server within QDash's time and memory limits; nothing is saved. details.data holds the full response with every cell.",
    promptSnippet: "Preview a metric script's per-qubit or per-pair results on a chip",
    promptGuidelines: [
      "Preview a metric script with qdash_preview_metric_script on the user's chip and period before saving it, and report missing and error cells, not only the values.",
      "Pass the draft as source; scriptId evaluates what is already saved (the active revision unless revision is given).",
    ],
    parameters: Type.Object({
      ...connectionParams,
      source: Type.Optional(Type.String({ description: "Draft source to evaluate. Give either source or scriptId." })),
      scriptId: Type.Optional(Type.String({ description: "Saved script to evaluate (ms_…)." })),
      revision: Type.Optional(Type.Number({ description: "With scriptId: a validated revision to evaluate instead of the active one." })),
      metricId: Type.String({ description: "The @metric function name to evaluate." }),
      chipId: Type.Optional(Type.String({ description: "Chip to evaluate on. Defaults to the session/default chip." })),
      period: Type.Optional(periodSchema),
      params: Type.Optional(Type.Object({}, { additionalProperties: true, description: "Parameter overrides by name; the rest use their defaults." })),
    }),
    async execute(
      _toolCallId,
      params: ConnectionParams & {
        source?: string;
        scriptId?: string;
        revision?: number;
        metricId: string;
        chipId?: string;
        period?: Period;
        params?: ParamValues;
      },
    ) {
      if (Boolean(params.source) === Boolean(params.scriptId)) {
        return toTextToolResult(
          "Give exactly one of source (a draft) or scriptId (a saved script). Nothing was evaluated.",
          { error: "source or scriptId" },
          { tool: "qdash_preview_metric_script", ok: false },
        );
      }
      const client = await deps.makeClient(params);
      const chipId = await deps.resolveChipId(client, params.chipId);
      const common = {
        metric_id: params.metricId,
        chip_id: chipId,
        ...(params.period ? { period: params.period } : {}),
        ...(params.params ? { params: params.params } : {}),
      };
      try {
        const result = (params.source
          ? await client.evaluateMetricScriptDraft({ source: params.source, ...common })
          : await client.evaluateMetricScript(params.scriptId as string, {
              ...common,
              ...(params.revision !== undefined ? { revision: params.revision } : {}),
            })) as unknown as EvaluateResponse;
        return toTextToolResult(formatEvaluation(result), result, {
          tool: "qdash_preview_metric_script",
          ok: true,
          chipId,
          metricId: result.metric.id,
          cellCount: result.cells.length,
          errorCount: result.cells.filter((cell) => cell.status === "error").length,
        });
      } catch (error) {
        return rejection("qdash_preview_metric_script", error, "evaluation", { chipId });
      }
    },
  });

  pi.registerTool({
    name: "qdash_save_metric_script",
    label: "QDash Save Metric Script",
    description:
      "Create a metric script (no scriptId) or save a new revision of one (scriptId). QDash validates the source on save: a valid revision becomes the active one; an invalid one is stored with its diagnostics while the last valid revision stays active. Dashboard panels pin a revision, so saving never changes a dashboard. Confirmation-gated write operation. The source is validated first, and a save that would not validate is refused without asking.",
    promptSnippet: "Save a metric script the user asked you to write",
    promptGuidelines: [
      "Before qdash_save_metric_script, validate and preview the source and show the user the whole code.",
      "When the user has the script open in the metric script editor, propose changes with propose_code_edit instead; save with qdash_save_metric_script only when they ask, because a save replaces their unsaved draft.",
      "Pass expectedRevision (the revision you read) when updating so a concurrent save is not overwritten.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      scriptId: Type.Optional(Type.String({ description: "Script to update (ms_…). Omit to create a new script." })),
      name: Type.String({ description: "Script name (1-120 characters)." }),
      description: Type.Optional(Type.String({ description: "Short description shown in the script list." })),
      visibility: Type.Optional(Type.Union([Type.Literal("private"), Type.Literal("project")], { description: "private (default for new scripts) or project. Project dashboards can only use project scripts." })),
      source: Type.String({ description: "The complete Python source (a qdash_metrics module)." }),
      expectedRevision: Type.Optional(Type.Number({ description: "Update only if the script is still at this revision (409 otherwise)." })),
      confirmWrite: Type.Optional(Type.Boolean({ description: "Required for non-interactive execution. Set true only after explicit user confirmation." })),
    }),
    async execute(
      _toolCallId,
      params: ConnectionParams & {
        scriptId?: string;
        name: string;
        description?: string;
        visibility?: "private" | "project";
        source: string;
        expectedRevision?: number;
        confirmWrite?: boolean;
      },
      _signal,
      _onUpdate,
      ctx,
    ) {
      const tool = "qdash_save_metric_script";
      const problems = scriptSaveProblems(params);
      if (problems.length) return problemResult(tool, problems, "metric script");
      const client = await deps.makeClient(params);
      let validation: ValidateResponse;
      try {
        validation = (await client.validateMetricScript(params.source)) as ValidateResponse;
      } catch (error) {
        return rejection(tool, error, "validation", { saved: false });
      }
      if (!validation.ok) {
        return toTextToolResult(
          [
            "The source does not validate, so it was not saved and no confirmation was asked. Fix these and validate again:",
            ...validation.diagnostics.map((diagnostic) => `- ${formatDiagnostic(diagnostic)}`),
          ].join("\n"),
          validation,
          { tool, saved: false, ok: false },
        );
      }
      if (!params.confirmWrite) {
        const what = params.scriptId ? `a new revision of metric script ${params.scriptId}` : `a new metric script '${params.name}'`;
        if (!ctx.hasUI || !(await ctx.ui.confirm("Save QDash metric script?", `This saves ${what} to the project.`))) {
          throw new Error(`${tool} requires explicit confirmation`);
        }
      }
      try {
        const created = !params.scriptId;
        const qdash = new QDash(client as QDashClient);
        const script = new Script({
          name: params.name,
          source: params.source,
          ...(params.description !== undefined ? { description: params.description } : {}),
          ...(params.visibility ? { visibility: params.visibility } : {}),
        });
        const saved = created
          ? await qdash.scripts.create(script)
          : await qdash.scripts.update(params.scriptId as string, script, {
              ...(params.expectedRevision !== undefined ? { expectedRevision: params.expectedRevision } : {}),
            });
        const result = saved.response as unknown as ScriptResponse;
        const page = url(client, metricScriptPagePath(result.script_id));
        return toTextToolResult(formatSavedScript(result, created, page), { ...result, url: page }, {
          tool,
          saved: true,
          created,
          scriptId: result.script_id,
          revision: result.revision,
          activeRevision: result.active_revision,
        });
      } catch (error) {
        return rejection(tool, error, "metric script", { saved: false });
      }
    },
  });

  pi.registerTool({
    name: "qdash_save_dashboard",
    label: "QDash Save Dashboard",
    description: [
      "Create a dashboard (no dashboardId) or update one (dashboardId). Confirmation-gated write operation.",
      "panels replaces the whole panel list on update: read the dashboard with qdash_query dashboard and send every panel.",
      "A panel is {panel_id, type, title, layout: {x, y, w, h}, config} on a 12-column grid (x + w <= 12, h 1-12).",
      "type metric_script: config {script_id, metric_id, script_revision, period, params, view, direction, hops}. script_revision is required and pins the panel to that saved revision (use the script's active_revision); later saves of the script do not change the panel.",
      "period is {kind: \"relative\", days} or {kind: \"absolute\", start, end} with timezones; params are the metric's Parameter values; view is \"map\" or \"table\"; direction (pair maps) is \"both\", \"forward\" or \"reverse\"; hops is a subset of [1, 2] within the metric's declared hops.",
      "Other types: qubit_metric and coupling_metric {metric: <metrics catalog key>}, markdown {content}.",
      "A project-visible dashboard cannot use private scripts. templateId (creation only) copies a starter template's panels when panels is empty.",
    ].join(" "),
    promptSnippet: "Create or update a dashboard with metric script panels",
    promptGuidelines: [
      "Pin metric_script panels to the script's active_revision from qdash_query metric_script, and say which revision a panel shows.",
      "On update, send the complete panels list; omitted panels are removed.",
      "Pass expectedVersion (the version you read) when updating so a concurrent save is not overwritten.",
      "When the user has the dashboard, or a new dashboard draft, open in QDash, propose changes with propose_code_edit instead; save with this tool only when they ask, because a save replaces their unsaved draft.",
    ],
    parameters: Type.Object({
      ...connectionParams,
      dashboardId: Type.Optional(Type.String({ description: "Dashboard to update. Omit to create one." })),
      name: Type.Optional(Type.String({ description: "Dashboard name; required to create." })),
      description: Type.Optional(Type.String()),
      visibility: Type.Optional(Type.Union([Type.Literal("private"), Type.Literal("project")])),
      chipId: Type.Optional(Type.String({ description: "Chip the dashboard shows." })),
      panels: Type.Optional(Type.Array(Type.Object({}, { additionalProperties: true }), { description: "The complete panel list (see the description for the shape)." })),
      templateId: Type.Optional(Type.String({ description: "Creation only: a starter template to copy panels from (qdash_query dashboard_templates)." })),
      expectedVersion: Type.Optional(Type.Number({ description: "Update only if the dashboard is still at this version (its `version` from qdash_query dashboard; 409 otherwise)." })),
      confirmWrite: Type.Optional(Type.Boolean({ description: "Required for non-interactive execution. Set true only after explicit user confirmation." })),
    }),
    async execute(
      _toolCallId,
      params: ConnectionParams & {
        dashboardId?: string;
        name?: string;
        description?: string;
        visibility?: "private" | "project";
        chipId?: string;
        panels?: Array<Record<string, unknown>>;
        templateId?: string;
        expectedVersion?: number;
        confirmWrite?: boolean;
      },
      _signal,
      _onUpdate,
      ctx,
    ) {
      const tool = "qdash_save_dashboard";
      const problems = dashboardSaveProblems(params);
      if (problems.length) return problemResult(tool, problems, "dashboard");
      if (!params.confirmWrite) {
        const what = params.dashboardId ? `dashboard ${params.dashboardId}` : `a new dashboard '${params.name}'`;
        if (!ctx.hasUI || !(await ctx.ui.confirm("Save QDash dashboard?", `This saves ${what} to the project.`))) {
          throw new Error(`${tool} requires explicit confirmation`);
        }
      }
      const client = await deps.makeClient(params);
      const panels = params.panels ? requestPanels(params.panels) : undefined;
      const fields = {
        ...(params.description !== undefined ? { description: params.description } : {}),
        ...(params.visibility ? { visibility: params.visibility } : {}),
        ...(params.chipId !== undefined ? { chip_id: params.chipId } : {}),
        ...(panels ? { panels } : {}),
      };
      try {
        const created = !params.dashboardId;
        const result = (created
          ? await client.createDashboard({
              name: params.name as string,
              ...fields,
              ...(params.templateId ? { template_id: params.templateId } : {}),
            } as Parameters<MetricScriptClient["createDashboard"]>[0])
          : await client.updateDashboard(params.dashboardId as string, {
              ...(params.name !== undefined ? { name: params.name } : {}),
              ...fields,
              ...(params.expectedVersion !== undefined ? { expected_version: params.expectedVersion } : {}),
            } as Parameters<MetricScriptClient["updateDashboard"]>[1])) as unknown as DashboardResponse;
        const page = url(client, dashboardPagePath(result.dashboard_id));
        return toTextToolResult(formatSavedDashboard(result, created, page), { ...result, url: page }, {
          tool,
          saved: true,
          created,
          dashboardId: result.dashboard_id,
          panelCount: result.panels.length,
        });
      } catch (error) {
        return rejection(tool, error, "dashboard", { saved: false });
      }
    },
  });
}
