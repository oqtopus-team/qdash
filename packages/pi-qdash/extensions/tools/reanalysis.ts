/**
 * `qdash_reanalyze_resonator_spectroscopy` and `qdash_reanalyze_qubit_spectroscopy`: re-run
 * the analysis of a stored CheckResonatorSpectroscopy or CheckQubitSpectroscopy result with
 * adjusted analysis parameters, through QDash's reanalyze routes.
 *
 * QDash re-reads the stored raw figure (or analyzes a raw Plotly figure the caller passes as
 * `figure`) and returns the re-estimated seed outputs and,
 * when asked, a PNG of the marked figure. It stores nothing and reserves no hardware, so
 * both tools are read-only: no approval, and code mode scripts may call them (a script
 * receives the structured outputs; the image is model-visible content only).
 *
 * The image is returned with the source task's name in `details.taskName`, so a following
 * `qcal_evaluate` for the same task evaluates the reanalyzed figure.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import type { QDashApi } from "@oqtopus-team/qdash-sdk";
import { Type } from "typebox";

import type { QDashConnection } from "../lib/qdash-connection.js";
import { CONFIG_PATH_DESCRIPTION, PROFILE_DESCRIPTION } from "../lib/connection.js";
import { qdashObjectLinks, qdashWebBaseUrl } from "../lib/links.js";
import { toFigureToolResult } from "../lib/results.js";

export const REANALYZE_RESONATOR_TOOL = "qdash_reanalyze_resonator_spectroscopy";
export const REANALYZE_QUBIT_TOOL = "qdash_reanalyze_qubit_spectroscopy";

type ConnectionParams = { profile?: string; configPath?: string; useEnv?: boolean };

type ReanalyzeParams<P> = ConnectionParams & {
  chipId?: string;
  qid: string;
  sourceTaskId?: string;
  figure?: Record<string, unknown>;
  parameters?: P;
  includeImage?: boolean;
};

export type ReanalysisDependencies = {
  makeClient(params: ConnectionParams): Promise<QDashConnection>;
  /**
   * The chip to use: the call's `chipId`, else the session's when the call connects where the
   * session does, else the connected server's default.
   */
  resolveChipId(client: QDashConnection, params: ConnectionParams & { chipId?: string }): Promise<string>;
};

type Json = Record<string, unknown>;

/** Output parameters by name, as QDash returned them. */
export type ReanalysisOutputs = Record<string, { value: number; unit: string }>;

/** What a reanalysis tool returns as data, also what a code mode script receives. */
export interface ReanalysisData {
  tool: string;
  chip_id: string;
  qid: string;
  task_name: string;
  /** The stored result analyzed, or null for an inline figure. */
  source_task_id: string | null;
  source_task_name: string;
  parameters: Json;
  outputs: ReanalysisOutputs;
  image: { requested: boolean; included: boolean; media_type?: string; error?: string };
  committed: false;
  links: Record<string, string>;
  note: string;
}

const PREVIEW_NOTE =
  "Preview only: QDash re-analyzed the stored data, stored nothing, and used no hardware. Treat the outputs as candidate seeds: check the figure (qcal_evaluate) and confirm them with a targeted measurement before relying on them.";

/** What the model reads when it asked for the image and QDash returned none. */
export function missingImageNote(taskName: string): string {
  return `Preview rendering failed, so no reanalyzed figure is attached. Do not call qcal_evaluate for ${taskName} now: it would evaluate an older stored figure of that task as if it were this reanalysis. Report the outputs as unverified, retry the reanalysis, or inspect the figure on the QDash task result page.`;
}

const connectionParams = {
  profile: Type.Optional(Type.String({ description: PROFILE_DESCRIPTION })),
  configPath: Type.Optional(Type.String({ description: CONFIG_PATH_DESCRIPTION })),
  useEnv: Type.Optional(Type.Boolean({ description: "Force QDASH_* environment variables instead of a profile." })),
};

function targetParams(taskName: string) {
  return {
    chipId: Type.Optional(Type.String({ description: "Chip ID. Defaults to the session's chip when the call uses the session's profile, else the connected server's default chip." })),
    qid: Type.String({ description: "Qubit ID, such as \"6\"." }),
    sourceTaskId: Type.Optional(
      Type.String({ description: `${taskName} task result to re-analyze. Defaults to the qubit's latest ${taskName} result; pass it to keep comparing the same measurement. Not with figure.` }),
    ),
    figure: Type.Optional(
      Type.Record(Type.String(), Type.Unknown(), {
        description: `A raw ${taskName} Plotly figure JSON object to analyze instead of a stored result, such as one a script read with qdash_analyze_figure_json includeData. The first trace must be the 2D heatmap (x in GHz, y in dB); a marked figure is rejected. Stored run parameters do not apply. At most 20 MiB. Not with sourceTaskId.`,
      }),
    ),
    includeImage: Type.Optional(
      Type.Boolean({ description: "Return a PNG of the re-analyzed marked figure as image content, for qcal_evaluate. Defaults to true; pass false from a code mode script, which receives no images." }),
    ),
  };
}

const resonatorParameters = Type.Object(
  {
    num_resonators: Type.Optional(Type.Integer({ minimum: 1, description: "Resonators to detect in the MUX (usually 4)." })),
    high_power_min: Type.Optional(Type.Number({ description: "Lower edge (dB) of the high-power (punched-out) region." })),
    high_power_max: Type.Optional(Type.Number({ description: "Upper edge (dB) of the high-power region." })),
    low_power: Type.Optional(Type.Number({ description: "Power (dB) sampled for the low-power (dressed) peaks." })),
    bare_shift_estimator_type: Type.Optional(
      Type.Union([Type.Literal("config"), Type.Literal("high_frequency_strength")], {
        description: "\"high_frequency_strength\" (the task's default) estimates the bare-shift boundary from the data and overrides the three power fields; \"config\" uses them as given.",
      }),
    ),
    bare_shift_strength_limit: Type.Optional(Type.Number({ description: "Strength cutoff of the high_frequency_strength estimator (default 4.0)." })),
    resonator_assignment_order: Type.Optional(
      Type.Array(Type.Integer({ minimum: 0, maximum: 3 }), {
        minItems: 4,
        maxItems: 4,
        description: "Qubit offsets in the MUX in increasing resonator-frequency order, each of 0..3 once. Defaults to the stored order.",
      }),
    ),
  },
  { description: "Analysis overrides, in QDash's snake_case names. A field left out keeps the stored task's value or the analysis default." },
);

const qubitParameters = Type.Object(
  {
    binarize_threshold_sigma_plus: Type.Optional(Type.Number({ description: "Upper binarization threshold in sigma (default 3.0)." })),
    binarize_threshold_sigma_minus: Type.Optional(Type.Number({ description: "Lower binarization threshold in sigma (default -2.0)." })),
    top_power: Type.Optional(Type.Number({ description: "Highest power row (dB) used by the analysis (default 0.0)." })),
    f01_height_min: Type.Optional(Type.Number({ description: "Smallest f01 feature height, in power rows times step (default 14.9)." })),
    f12_distance_min: Type.Optional(Type.Number({ description: "Smallest f01-f12 distance (GHz) searched for f12." })),
    f12_distance_max: Type.Optional(Type.Number({ description: "Largest f01-f12 distance (GHz) searched for f12." })),
    f12_height_min: Type.Optional(Type.Number({ description: "Smallest f12 feature height." })),
    retry_with_trim: Type.Optional(Type.Boolean({ description: "Retry after trimming the highest-power row (and then one more) when no f01 is found." })),
  },
  { description: "Analysis overrides, in QDash's snake_case names. A field left out keeps the stored task's value or the analysis default." },
);

type ResonatorParameters = QDashApi.ReanalyzeResonatorSpectroscopyParams;
type QubitParameters = QDashApi.ReanalyzeQubitSpectroscopyParams;

function formatNumber(value: number): string {
  if (!Number.isFinite(value)) return String(value);
  return Math.abs(value) >= 1e-3 || value === 0 ? String(Number(value.toPrecision(7))) : value.toExponential(4);
}

function definedEntries(object: object | undefined): Json {
  return Object.fromEntries(Object.entries(object ?? {}).filter(([, value]) => value !== undefined && value !== null));
}

/** The response as tool data: outputs by name, no Plotly figure, the image reduced to its status. */
export function reanalysisData(
  tool: string,
  taskName: string,
  chipId: string,
  response: QDashApi.ReanalyzeResponse,
  parameters: Json,
  imageRequested: boolean,
  links: Record<string, string>,
): ReanalysisData {
  const outputs: ReanalysisOutputs = {};
  for (const output of response.output_parameters ?? []) outputs[output.name] = { value: output.value, unit: output.unit ?? "" };
  const included = imageRequested && typeof response.image_base64 === "string" && response.image_base64.length > 0;
  return {
    tool,
    chip_id: chipId,
    qid: response.qid,
    task_name: taskName,
    source_task_id: response.source_task_id ?? null,
    source_task_name: response.source_task_name,
    parameters,
    outputs,
    image: {
      requested: imageRequested,
      included,
      ...(included ? { media_type: response.image_media_type ?? "image/png" } : {}),
      ...(imageRequested && !included ? { error: response.image_error ?? "QDash returned no image." } : {}),
    },
    committed: false,
    links,
    note: PREVIEW_NOTE,
  };
}

/** A short summary of the reanalysis for the model, followed by its data. */
export function reanalysisText(data: ReanalysisData): string {
  const outputs = Object.entries(data.outputs).map(([name, { value, unit }]) => `${name}=${formatNumber(value)}${unit ? ` ${unit}` : ""}`);
  const overrides = Object.entries(data.parameters).map(([name, value]) => `${name}=${JSON.stringify(value)}`);
  const image = !data.image.requested
    ? "not requested"
    : data.image.included
      ? `attached (${data.image.media_type}); qcal_evaluate with task_name "${data.task_name}" evaluates it`
      : `unavailable: ${data.image.error}`;
  const links = Object.entries(data.links).map(([name, url]) => `${name} ${url}`);
  return [
    data.source_task_id
      ? `Reanalyzed ${data.source_task_name} result ${data.source_task_id} for qubit ${data.qid} on chip ${data.chip_id}.`
      : `Reanalyzed an inline ${data.source_task_name} figure (no stored task result) for qubit ${data.qid} on chip ${data.chip_id}.`,
    `overrides: ${overrides.length ? overrides.join(", ") : "none (stored settings and analysis defaults)"}`,
    `outputs: ${outputs.length ? outputs.join(", ") : "none: the analysis found no feature with these settings"}`,
    `image: ${image}`,
    ...(data.image.requested && !data.image.included ? [missingImageNote(data.task_name)] : []),
    data.note,
    ...(links.length ? [`links: ${links.join("  ")}`] : []),
    "",
    JSON.stringify(data, null, 2),
  ].join("\n");
}

function registerReanalysisTool<P extends object>(
  pi: Pick<ExtensionAPI, "registerTool">,
  deps: ReanalysisDependencies,
  spec: {
    name: string;
    label: string;
    taskName: string;
    description: string;
    promptSnippet: string;
    promptGuidelines: string[];
    parameters: typeof resonatorParameters | typeof qubitParameters;
    call(client: QDashConnection, chipId: string, qid: string, body: { source_task_id?: string; figure?: Record<string, unknown>; parameters?: P; include_image: boolean }, signal?: AbortSignal): Promise<QDashApi.ReanalyzeResponse>;
  },
): void {
  pi.registerTool({
    name: spec.name,
    label: spec.label,
    description: spec.description,
    promptSnippet: spec.promptSnippet,
    promptGuidelines: spec.promptGuidelines,
    parameters: Type.Object({
      ...connectionParams,
      ...targetParams(spec.taskName),
      parameters: Type.Optional(spec.parameters),
    }),
    async execute(_toolCallId, params: ReanalyzeParams<P>, signal) {
      if (params.sourceTaskId && params.figure) {
        throw new Error(`${spec.name} takes either sourceTaskId or figure, not both. Pass sourceTaskId to re-analyze a stored result, or figure for a Plotly figure you already have.`);
      }
      const client = await deps.makeClient(params);
      const chipId = await deps.resolveChipId(client, params);
      const includeImage = params.includeImage !== false;
      const parameters = definedEntries(params.parameters);
      const response = await spec.call(
        client,
        chipId,
        params.qid,
        {
          ...(params.sourceTaskId ? { source_task_id: params.sourceTaskId } : {}),
          ...(params.figure ? { figure: params.figure } : {}),
          ...(Object.keys(parameters).length ? { parameters: parameters as P } : {}),
          include_image: includeImage,
        },
        signal,
      );
      const sourceTaskId = response.source_task_id ?? undefined;
      const links = sourceTaskId ? qdashObjectLinks(client, { task_id: sourceTaskId, chip_id: chipId }) : {};
      const data = reanalysisData(spec.name, spec.taskName, chipId, response, parameters, includeImage, links);
      const figure = data.image.included
        ? { base64: response.image_base64 as string, mediaType: data.image.media_type as string }
        : { mediaType: "" };
      return toFigureToolResult(reanalysisText(data), figure, data, {
        tool: spec.name,
        // qcal_evaluate takes the newest figure recorded for the task it evaluates.
        // An inline figure has no task result; its task name still routes it to qcal_evaluate.
        ...(sourceTaskId ? { taskId: sourceTaskId } : {}),
        taskName: response.source_task_name,
        webBaseUrl: qdashWebBaseUrl(client),
      });
    },
  });
}

export function registerReanalysisTools(pi: Pick<ExtensionAPI, "registerTool">, deps: ReanalysisDependencies): void {
  registerReanalysisTool<ResonatorParameters>(pi, deps, {
    name: REANALYZE_RESONATOR_TOOL,
    label: "QDash Reanalyze Resonator Spectroscopy",
    taskName: "CheckResonatorSpectroscopy",
    description:
      "Re-run the analysis of a stored CheckResonatorSpectroscopy result for one qubit with adjusted analysis parameters (power region, bare-shift estimator, resonator assignment order) and return the re-estimated readout_frequency, optimal_power (dB), and readout_amplitude (a.u.), with the marked figure as an image. Pass figure instead to analyze a raw Plotly figure JSON you already have. Read-only preview: QDash stores nothing and uses no hardware.",
    promptSnippet: "Re-analyze a stored resonator spectroscopy result with adjusted analysis parameters (preview, no hardware)",
    promptGuidelines: [
      `Use ${REANALYZE_RESONATOR_TOOL} when a resonator spectroscopy result shows a real resonance that the analysis missed or assigned to the wrong qubit; adjust the analysis parameters instead of measuring again.`,
      `${REANALYZE_RESONATOR_TOOL} changes nothing in QDash: treat its outputs as candidates, check the returned figure with qcal_evaluate, and confirm them with a targeted measurement before committing.`,
    ],
    parameters: resonatorParameters,
    call: (client, chipId, qid, body, signal) => client.reanalyzeResonatorSpectroscopy(chipId, qid, body, signal),
  });
  registerReanalysisTool<QubitParameters>(pi, deps, {
    name: REANALYZE_QUBIT_TOOL,
    label: "QDash Reanalyze Qubit Spectroscopy",
    taskName: "CheckQubitSpectroscopy",
    description:
      "Re-run the analysis of a stored CheckQubitSpectroscopy result for one qubit with adjusted analysis parameters (binarization thresholds, top power, f01 and f12 limits, trim retry) and return the re-estimated coarse_qubit_frequency, coarse_control_amplitude, f01_repr_db, and f01_quality_level, with the marked figure as an image. Pass figure instead to analyze a raw Plotly figure JSON you already have. Read-only preview: QDash stores nothing and uses no hardware.",
    promptSnippet: "Re-analyze a stored qubit spectroscopy result with adjusted analysis parameters (preview, no hardware)",
    promptGuidelines: [
      `Use ${REANALYZE_QUBIT_TOOL} when a qubit spectroscopy figure shows a real f01 line that the analysis missed, marked in the wrong place, or rated low; adjust the analysis parameters instead of measuring again.`,
      `${REANALYZE_QUBIT_TOOL} changes nothing in QDash: treat coarse_qubit_frequency and coarse_control_amplitude as seeds, check the returned figure with qcal_evaluate, and confirm them on hardware (for example CheckControlAmplitude then CheckAdaptiveChevron) before committing.`,
    ],
    parameters: qubitParameters,
    call: (client, chipId, qid, body, signal) => client.reanalyzeQubitSpectroscopy(chipId, qid, body, signal),
  });
}
