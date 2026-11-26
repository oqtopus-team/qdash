/**
 * Compound reads of task results: operations that combine several client
 * calls into one answer, such as comparing a target's latest repeated results.
 */
import { isDeepStrictEqual } from "node:util";

import { isRecord, read, type Context } from "./_http.js";
import { QDashApiError, QDashValidationError } from "./errors.js";
import type { TaskResultListItem, TaskResultListResponse, TaskResultResponse } from "./types.js";
import { readTaskResultEvidence, type TaskResultEvidence, type TaskResultEvidenceOptions } from "./evidence.js";

/** List rows `compareLatest` reads when `limit` is omitted. */
export const COMPARE_LATEST_DEFAULT_ROWS = 20;
/** Most list rows `compareLatest` reads: one `GET /task-results` page. */
export const COMPARE_LATEST_MAX_ROWS = 100;
// Tasks whose two details are read at the same time.
const DETAIL_READ_CONCURRENCY = 4;
const COMPARE_LATEST_OPTIONS = new Set(["chipId", "qid", "limit"]);

export interface CompareLatestOptions {
  chipId: string;
  /** Exact qubit (`"6"`) or coupling (`"6-7"`) ID as QDash stores it; the list's `qid` filter. */
  qid: string;
  /** Newest list rows to read, an integer from 2 to 100. Defaults to 20. */
  limit?: number;
}

/** One output parameter whose value differs; a parameter missing on one side is `undefined` there. */
export interface OutputParameterChange {
  before: unknown;
  after: unknown;
}

/** The two newest results of one task name. */
export interface ComparedTaskResults {
  task: string;
  /** The older list row. */
  before: TaskResultListItem;
  /** The newer list row. */
  after: TaskResultListItem;
  /**
   * `compared` when both details were read and match their rows;
   * `unavailable` when either was not, with `changes` null and `error` saying why.
   */
  status: "compared" | "unavailable";
  /** Output parameters whose value differs, by name; empty only when every value agrees. */
  changes: Record<string, OutputParameterChange> | null;
  error?: string;
}

export interface TaskResultComparison {
  chipId: string;
  qid: string;
  /** List rows read, and how many matched the filters in total. */
  rows: { read: number; total: number };
  /** Task names with at least two results among the rows read, in the order their newest result appears. */
  compared: ComparedTaskResults[];
  /** Task names with fewer than two results among the rows read. */
  insufficient: Array<{ task: string; results: number }>;
}

function checkCompareLatestOptions(options: CompareLatestOptions): number {
  const problems: string[] = [];
  const raw = (options ?? {}) as unknown as Record<string, unknown>;
  for (const field of ["chipId", "qid"]) {
    const value = raw[field];
    if (typeof value !== "string" || value.trim() === "") problems.push(`${field} is required`);
  }
  const limit = raw.limit ?? COMPARE_LATEST_DEFAULT_ROWS;
  if (!(Number.isInteger(limit) && (limit as number) >= 2 && (limit as number) <= COMPARE_LATEST_MAX_ROWS)) {
    problems.push(`limit must be an integer from 2 to ${COMPARE_LATEST_MAX_ROWS} (got ${JSON.stringify(raw.limit)})`);
  }
  const unknown = Object.keys(raw).filter((key) => raw[key] !== undefined && !COMPARE_LATEST_OPTIONS.has(key));
  if (unknown.length > 0) {
    problems.push(`${unknown.join(", ")} ${unknown.length === 1 ? "is not an option" : "are not options"} of compareLatest`);
  }
  if (problems.length > 0) {
    throw new QDashValidationError(`${problems.join("; ")}.`, { body: { problems } });
  }
  return limit as number;
}

/** The compared value of one output parameter: its `value` field, or the parameter itself when it is a bare value. */
function parameterValue(value: unknown): unknown {
  return isRecord(value) && "value" in value ? value.value : value;
}

/**
 * Output parameters whose value differs. Values compare structurally: object
 * key order is ignored, array order is not, and `error`, `unit` or
 * `calibrated_at` alone are not a change.
 */
function outputParameterChanges(
  before: Record<string, unknown>,
  after: Record<string, unknown>,
): Record<string, OutputParameterChange> {
  const changes: Record<string, OutputParameterChange> = {};
  for (const name of new Set([...Object.keys(before), ...Object.keys(after)])) {
    const beforeValue = parameterValue(before[name]);
    const afterValue = parameterValue(after[name]);
    if (!isDeepStrictEqual(beforeValue, afterValue)) changes[name] = { before: beforeValue, after: afterValue };
  }
  return changes;
}

/** The output parameters of the detail read for `row`, or why they cannot be used. */
function detailParameters(detail: TaskResultResponse, row: TaskResultListItem): Record<string, unknown> | string {
  // The body is checked at run time: a server that answers with another shape must not read as "no change".
  const body: unknown = detail;
  const taskId = row.task_id;
  if (!isRecord(body)) return `the result of ${taskId} is not an object`;
  if (body.task_id !== taskId) return `the result read for ${taskId} has task_id ${JSON.stringify(body.task_id)}`;
  if (body.task_name !== row.task_name) {
    return `the result of ${taskId} has task_name ${JSON.stringify(body.task_name)}, not ${JSON.stringify(row.task_name)}`;
  }
  if (body.qid !== row.qid) return `the result of ${taskId} has qid ${JSON.stringify(body.qid)}, not ${JSON.stringify(row.qid)}`;
  if (body.chip_id !== row.chip_id) return `the result of ${taskId} has chip_id ${JSON.stringify(body.chip_id)}, not ${JSON.stringify(row.chip_id)}`;
  if (!isRecord(body.output_parameters)) return `the result of ${taskId} has no output_parameters object`;
  return body.output_parameters;
}

async function mapConcurrently<T, R>(items: readonly T[], limit: number, map: (item: T) => Promise<R>): Promise<R[]> {
  const results = new Array<R>(items.length);
  let next = 0;
  const worker = async () => {
    while (next < items.length) {
      const index = next++;
      results[index] = await map(items[index]!);
    }
  };
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  return results;
}

/** Task results read through a session; `qdash.taskResults`. */
export class TaskResults {
  constructor(private readonly context: Context) {}

  /**
   * Compare the latest two results of each task name for one qubit or coupling.
   *
   * Reads the newest `limit` rows of `GET /task-results` for `chipId` and `qid`
   * (newest first, as the API orders them). List rows carry no output
   * parameters, so for each task name with at least two rows the newest row is
   * `after`, the next is `before`, and both details are read with
   * `GET /tasks/{task_id}/result`. A detail that fails, is not an object, has no
   * `output_parameters` object, or names another task ID, task name or qid
   * makes that task `unavailable`; it is never reported as unchanged. A task
   * with one row is listed in `insufficient` and no detail is read for it.
   *
   * Invalid options throw `QDashValidationError` before any request; a failed
   * list read rejects the call, and a list row without a `task_name` throws
   * `QDashApiError`.
   */
  async compareLatest(options: CompareLatestOptions): Promise<TaskResultComparison> {
    const limit = checkCompareLatestOptions(options);
    const { chipId, qid } = options;
    const page = await this.listPage(chipId, qid, limit);
    const groups = new Map<string, TaskResultListItem[]>();
    for (const row of page.items) {
      const task: unknown = row.task_name;
      if (typeof task !== "string" || task === "") {
        throw new QDashApiError(`Unexpected GET /task-results response: row ${row.task_id} has no task_name`, {
          body: row,
        });
      }
      groups.set(task, [...(groups.get(task) ?? []), row]);
    }
    const insufficient: TaskResultComparison["insufficient"] = [];
    const pairs: Array<{ task: string; after: TaskResultListItem; before: TaskResultListItem }> = [];
    for (const [task, rows] of groups) {
      if (rows.length < 2) insufficient.push({ task, results: rows.length });
      else pairs.push({ task, after: rows[0]!, before: rows[1]! });
    }
    const compared = await mapConcurrently(pairs, DETAIL_READ_CONCURRENCY, async ({ task, after, before }) => {
      const [beforeParameters, afterParameters] = await Promise.all([this.parameters(before), this.parameters(after)]);
      if (typeof beforeParameters === "string" || typeof afterParameters === "string") {
        const error = [beforeParameters, afterParameters].filter((value) => typeof value === "string").join("; ");
        return { task, before, after, status: "unavailable" as const, changes: null, error };
      }
      return {
        task,
        before,
        after,
        status: "compared" as const,
        changes: outputParameterChanges(beforeParameters, afterParameters),
      };
    });
    return { chipId, qid, rows: { read: page.items.length, total: page.total }, compared, insufficient };
  }

  /**
   * Read one task result with the context to interpret it.
   *
   * Reads `GET /tasks/{task_id}/result`, then the execution it names (with this
   * result's entry in it), the current state of its qubit or coupling with the
   * stored values of the parameters it outputs, and the cooldown named by
   * `cooldownId`, checked against the result's chip and start time. QDash's
   * task result does not record its cooldown, so without `cooldownId` the
   * cooldown part is `not_associated`; none is inferred.
   *
   * Every context part reports `ok`, `failed`, `not_applicable` or
   * `not_associated` (`TaskResultContext`); a failed part is never filled from
   * other data. Invalid arguments throw `QDashValidationError` before any
   * request; a failed result read rejects the call, and a result that is not an
   * object or names another task ID throws `QDashApiError`.
   */
  evidence(taskId: string, options: TaskResultEvidenceOptions = {}): Promise<TaskResultEvidence> {
    return readTaskResultEvidence(this.context, taskId, options);
  }

  /** One page of `GET /task-results`, or an error naming what is missing; never an empty page in place of a malformed one. */
  private async listPage(chipId: string, qid: string, limit: number): Promise<TaskResultListResponse> {
    const payload: unknown = await read(this.context.reads, (requestOptions) =>
      this.context.api.taskResult.listTaskResults({ chip_id: chipId, qid, limit }, requestOptions),
    );
    const page = payload as Partial<TaskResultListResponse> | null;
    const problems: string[] = [];
    if (!isRecord(page)) problems.push("the body is not an object");
    else {
      if (!Array.isArray(page.items)) problems.push("items is not an array");
      else if (page.items.some((item) => !isRecord(item) || typeof item.task_id !== "string")) problems.push("an item has no task_id");
      if (!Number.isInteger(page.total)) problems.push("total is not an integer");
    }
    if (problems.length > 0) {
      throw new QDashApiError(`Unexpected GET /task-results response: ${problems.join("; ")}`, { body: payload });
    }
    return page as TaskResultListResponse;
  }

  private async parameters(row: TaskResultListItem): Promise<Record<string, unknown> | string> {
    try {
      const detail = await read(this.context.reads, (requestOptions) =>
        this.context.api.task.getTaskResult({ task_id: row.task_id }, requestOptions),
      );
      return detailParameters(detail, row);
    } catch (error) {
      return `reading the result of ${row.task_id} failed: ${error instanceof Error ? error.message : String(error)}`;
    }
  }
}
