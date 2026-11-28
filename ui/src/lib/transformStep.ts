import type { TransformStepRecord } from "@/schemas";

/**
 * A pipeline step that only selects or plans (a filter or a CR schedule). The worker records it
 * in its own execution, marked `note.step_kind = "transform"`, with no tasks and no hardware;
 * its outcome is `note.transform_result`. Executions recorded before then carry neither.
 */
export function isTransformExecution(note: unknown): boolean {
  return (
    !!note &&
    typeof note === "object" &&
    (note as { step_kind?: unknown }).step_kind === "transform"
  );
}

/** The recorded outcome of a transform step's execution, or null when it has none. */
export function transformRecordOf(note: unknown): TransformStepRecord | null {
  if (!isRecord(note)) return null;
  const record = note.transform_result;
  if (!isRecord(record)) return null;
  if (!["filter", "cr_schedule", "transform"].includes(record.kind as string)) return null;

  for (const key of ["input_qids", "output_qids", "input_couplings", "output_couplings"]) {
    if (record[key] !== undefined && !isStringArray(record[key])) return null;
  }
  if (
    record.excluded !== undefined &&
    (!Array.isArray(record.excluded) ||
      !record.excluded.every(
        (entry) =>
          isRecord(entry) && typeof entry.target === "string" && typeof entry.reason === "string",
      ))
  )
    return null;
  if (
    record.groups != null &&
    (!Array.isArray(record.groups) || !record.groups.every(isStringArray))
  )
    return null;
  for (const key of [
    "criteria",
    "source_step",
    "source_call_id",
    "metric",
    "direction",
    "message",
  ]) {
    if (record[key] != null && typeof record[key] !== "string") return null;
  }
  for (const key of ["threshold", "max_parallel_ops"]) {
    const value = record[key];
    if (value != null && (typeof value !== "number" || !Number.isFinite(value))) return null;
  }
  if (record.max_parallel_ops != null && !Number.isInteger(record.max_parallel_ops)) return null;
  if (record.source_found != null && typeof record.source_found !== "boolean") return null;
  return record as unknown as TransformStepRecord;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((entry) => typeof entry === "string");
}

function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

/** One line saying what a transform step decided, from its record alone. */
export function transformSummary(record: TransformStepRecord): string {
  if (record.kind === "cr_schedule") {
    const groups = record.groups ?? [];
    if (groups.length === 0) return record.message || "No CR pair scheduled";
    const pairs = groups.reduce((sum, group) => sum + group.length, 0);
    return `${plural(pairs, "pair")} in ${plural(groups.length, "group")}`;
  }
  const input = record.input_qids ?? [];
  const output = record.output_qids ?? [];
  if (record.kind === "filter" && record.source_found === false) {
    return record.message || "No result to filter by; every candidate kept";
  }
  return `Kept ${output.length} of ${plural(input.length, "qubit")}`;
}
