/**
 * Output-parameter comparison of a target's repeated task results, the data
 * `qdash_compare_calibration` returns.
 *
 * `GET /task-results` rows (`TaskResultListItem`) carry no output parameters,
 * so the rows only select which results to compare: per task name, the newest
 * row is `after` and the next is `before` (the list is newest first). Each
 * selected result's parameters come from `GET /tasks/{task_id}/result`
 * (`TaskResultResponse`). A detail that fails, or that does not match the row
 * it was read for, makes that task `unavailable` with the reason; it is never
 * reported as an unchanged result.
 */

import { isDeepStrictEqual } from "node:util";

/** A `GET /task-results` row, as the list returns it. */
export type TaskResultRow = Record<string, unknown>;

export type ParameterChange = { before: unknown; after: unknown };

export type ComparedTask = {
  task: string;
  /** The older list row. */
  before: TaskResultRow;
  /** The newer list row. */
  after: TaskResultRow;
  /**
   * `compared` when both details were read and checked; `unavailable` when
   * either was not, in which case `changes` is null and `error` says why.
   */
  status: "compared" | "unavailable";
  /** Output parameters whose `value` differs, by name; empty only when both details agree. */
  changes: Record<string, ParameterChange> | null;
  error?: string;
};

export type RepeatedTaskComparison = {
  compared: ComparedTask[];
  /** Tasks with fewer than two results among the rows read. */
  insufficient: Array<{ task: string; results: number }>;
};

/** Reads one task result detail, as `GET /tasks/{task_id}/result` returns it. */
export type TaskResultDetailReader = (taskId: string) => Promise<unknown>;

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

function rowTask(row: TaskResultRow): string {
  return typeof row.task_name === "string" && row.task_name !== "" ? row.task_name : "task";
}

/** The compared value of one output parameter: its `value` field, or the parameter itself when it is a bare value. */
export function parameterValue(value: unknown): unknown {
  if (isRecord(value) && "value" in value) return value.value;
  return value;
}

/** The output parameters of a detail read for `taskId` and `task`, or the reason they cannot be used. */
function detailParameters(detail: unknown, taskId: string, task: string): Record<string, unknown> | string {
  if (!isRecord(detail)) return `the result of ${taskId} is not an object`;
  if (detail.task_id !== taskId) return `the result read for ${taskId} has task_id ${JSON.stringify(detail.task_id)}`;
  if (task !== "task" && detail.task_name !== task) return `the result of ${taskId} has task_name ${JSON.stringify(detail.task_name)}, not ${JSON.stringify(task)}`;
  if (!isRecord(detail.output_parameters)) return `the result of ${taskId} has no output_parameters object`;
  return detail.output_parameters;
}

export function diffOutputParameters(before: Record<string, unknown>, after: Record<string, unknown>): Record<string, ParameterChange> {
  const changes: Record<string, ParameterChange> = {};
  for (const name of new Set([...Object.keys(before), ...Object.keys(after)])) {
    const beforeValue = parameterValue(before[name]);
    const afterValue = parameterValue(after[name]);
    if (!isDeepStrictEqual(beforeValue, afterValue)) changes[name] = { before: beforeValue, after: afterValue };
  }
  return changes;
}

async function readParameters(read: TaskResultDetailReader, row: TaskResultRow, task: string): Promise<Record<string, unknown> | string> {
  const taskId = row.task_id;
  if (typeof taskId !== "string" || taskId === "") return "a list row has no task_id";
  try {
    return detailParameters(await read(taskId), taskId, task);
  } catch (error) {
    return `reading the result of ${taskId} failed: ${error instanceof Error ? error.message : String(error)}`;
  }
}

/**
 * Compares the two newest results of each task name in `rows` (newest first).
 * Details are read concurrently, two per task with at least two rows.
 */
export async function compareRepeatedTaskResults(rows: TaskResultRow[], read: TaskResultDetailReader): Promise<RepeatedTaskComparison> {
  const groups = new Map<string, TaskResultRow[]>();
  for (const row of rows) {
    const task = rowTask(row);
    groups.set(task, [...(groups.get(task) ?? []), row]);
  }
  const insufficient: RepeatedTaskComparison["insufficient"] = [];
  const pairs: Array<{ task: string; after: TaskResultRow; before: TaskResultRow }> = [];
  for (const [task, entries] of groups) {
    if (entries.length < 2) insufficient.push({ task, results: entries.length });
    else pairs.push({ task, after: entries[0], before: entries[1] });
  }
  const compared = await Promise.all(pairs.map(async ({ task, after, before }): Promise<ComparedTask> => {
    const [beforeParams, afterParams] = await Promise.all([readParameters(read, before, task), readParameters(read, after, task)]);
    const problems = [beforeParams, afterParams].filter((value): value is string => typeof value === "string");
    if (problems.length > 0) return { task, before, after, status: "unavailable", changes: null, error: problems.join("; ") };
    return { task, before, after, status: "compared", changes: diffOutputParameters(beforeParams as Record<string, unknown>, afterParams as Record<string, unknown>) };
  }));
  return { compared, insufficient };
}
