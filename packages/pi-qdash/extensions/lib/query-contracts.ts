/**
 * Response contracts of the task-result list, chip metrics, and timeseries
 * queries: the data `qdash_list_task_results`, `qdash_get_chip_metrics`,
 * `qdash_get_timeseries` and the matching `qdash_query` actions return.
 *
 * Each schema is the tool's output schema, so a code mode script's tool
 * declaration shows the real shape in both hosts, and pi-qdash checks every
 * response against it before returning: a response of another shape fails
 * the call with the path that differs instead of reaching a script that would
 * read it as empty. The schemas follow the API models
 * (`TaskResultListResponse`, `ChipMetricsResponse`, `TimeSeriesData` under
 * `src/qdash/api/schemas/`) and allow extra fields, such as pi-qdash's
 * `_links`.
 */
import { Type, type TSchema } from "typebox";
import { Value } from "typebox/value";

const nullable = (schema: TSchema, description?: string) =>
  Type.Union([schema, Type.Null()], description ? { description } : {});

/** A map with arbitrary keys; `additionalProperties` renders as `[key: string]: T` in tool declarations. */
const keyed = (value: TSchema, description?: string) =>
  Type.Object({}, { additionalProperties: value, ...(description ? { description } : {}) });

/** Most rows one task-result request returns. */
export const TASK_RESULTS_PAGE_LIMIT = 100;

const TASK_RESULT_ROW = Type.Object({
  task_id: Type.String(),
  task_name: Type.String(),
  qid: Type.String(),
  chip_id: Type.String(),
  status: Type.String(),
  execution_id: Type.String(),
  message: Type.Optional(Type.String()),
  start_at: Type.Optional(nullable(Type.String())),
  end_at: Type.Optional(nullable(Type.String())),
});

export const TASK_RESULT_PAGE_SCHEMA = Type.Object({
  items: Type.Array(TASK_RESULT_ROW, {
    description:
      "One page, newest first (start_at desc). No output parameters: read one with qdash_get_task_result. The newest row per task here is only the newest in this page unless skip + items.length >= total.",
  }),
  total: Type.Integer({ description: "Rows matching the filters across all pages." }),
  skip: Type.Integer(),
  limit: Type.Integer(),
  status_counts: keyed(
    Type.Integer(),
    "Rows per status across all pages, counted without the status filter: with status set, it is not limited to that status.",
  ),
});

const METRIC_VALUE = Type.Object({
  value: nullable(Type.Number()),
  task_id: nullable(Type.String()),
  execution_id: nullable(Type.String()),
  stddev: nullable(Type.Number()),
});

const METRIC_MAP_DESCRIPTION =
  "metric key -> target ID -> value, e.g. qubit_metrics.t1[\"6\"]. Keys are metrics_config names and target IDs exactly as QDash stores them; a target without a value is absent. No timestamps: follow task_id with qdash_get_task_result.";

export const CHIP_METRICS_SCHEMA = Type.Object({
  chip_id: Type.String(),
  qubit_count: Type.Integer(),
  within_hours: Type.Optional(nullable(Type.Integer())),
  start_at: Type.Optional(nullable(Type.String(), "Lower bound of the query window, not a calibration time.")),
  end_at: Type.Optional(nullable(Type.String(), "Upper bound of the query window, not a calibration time.")),
  qubit_metrics: keyed(keyed(METRIC_VALUE), METRIC_MAP_DESCRIPTION),
  coupling_metrics: keyed(keyed(METRIC_VALUE), "As qubit_metrics, keyed by coupling ID such as \"6-7\"."),
});

const TIMESERIES_POINT = Type.Object({
  value: nullable(Type.Number()),
  error: Type.Optional(Type.Number()),
  unit: Type.Optional(Type.String()),
  calibrated_at: Type.Optional(Type.String()),
  execution_id: Type.Optional(Type.String()),
  task_id: Type.Optional(Type.String()),
});

export const TIMESERIES_SCHEMA = Type.Object({
  data: keyed(
    Type.Array(TIMESERIES_POINT),
    "target ID -> points in task start order (oldest first), e.g. data[\"6\"]. An object, not an array, also with qid set; a target without points in the window is absent.",
  ),
});

/** Output schema of each query action with a checked contract. */
export const QUERY_CONTRACTS = {
  task_results: TASK_RESULT_PAGE_SCHEMA,
  chip_metrics: CHIP_METRICS_SCHEMA,
  timeseries: TIMESERIES_SCHEMA,
} as const;

export type ContractedAction = keyof typeof QUERY_CONTRACTS;

export function isContractedAction(action: string): action is ContractedAction {
  return Object.hasOwn(QUERY_CONTRACTS, action);
}

/**
 * Why `limit` or `skip` of a task-result query cannot be sent, as advice the
 * caller can act on, or null when both are valid. Checked before any request.
 */
export function taskResultPageProblem(params: { limit?: unknown; skip?: unknown }): string | null {
  const problems: string[] = [];
  const { limit, skip } = params;
  if (limit !== undefined && !(Number.isInteger(limit) && (limit as number) >= 1 && (limit as number) <= TASK_RESULTS_PAGE_LIMIT)) {
    problems.push(`limit must be an integer from 1 to ${TASK_RESULTS_PAGE_LIMIT} (got ${JSON.stringify(limit)})`);
  }
  if (skip !== undefined && !(Number.isInteger(skip) && (skip as number) >= 0)) {
    problems.push(`skip must be an integer of 0 or more (got ${JSON.stringify(skip)})`);
  }
  if (problems.length === 0) return null;
  return `${problems.join("; ")}. No request was sent. QDash returns at most ${TASK_RESULTS_PAGE_LIMIT} task results per call: for more, call again with skip increased by the rows already read (skip 0, then 100, ...) until skip >= total or a page has fewer rows than limit.`;
}

/**
 * The response unchanged when it has the documented shape; otherwise an error
 * naming where it differs. Never substitutes an empty value.
 */
export function checkQueryResponse(action: ContractedAction, data: unknown): unknown {
  const schema = QUERY_CONTRACTS[action];
  if (Value.Check(schema, data)) return data;
  const seen = new Set<string>();
  const lines: string[] = [];
  for (const error of Value.Errors(schema, data)) {
    const path = error.instancePath || "/";
    if (seen.has(path)) continue;
    seen.add(path);
    lines.push(`${path}: ${error.message}`);
    if (lines.length === 3) break;
  }
  throw new Error(
    `QDash returned a ${action} response that does not match its documented shape (${lines.join("; ")}). This is not empty data; report it instead of treating it as no results.`,
  );
}

/**
 * Why a `qubit_history` or `coupling_history` query cannot be sent, or null
 * when it can. The history routes take no date, and the client's
 * `getQubitTaskHistory` and `getCouplingTaskHistory` refuse one for every
 * caller. `qdash_query` shares one `date` argument across actions, so this host
 * check refuses it first, before the default chip is resolved, with advice in
 * tool terms.
 */
export function targetHistoryProblem(params: { action: "qubit_history" | "coupling_history"; date?: unknown }): string | null {
  if (params.date === undefined) return null;
  const target = params.action === "qubit_history" ? "qid" : "couplingId";
  return `date cannot filter ${params.action}: it returns every result of the task for one target, newest first, with no date filter. Omit date to read the whole history, or use the task_results action (or qdash_list_task_results) with ${target}, taskName, startFrom and startTo for one period. No request was sent.`;
}
