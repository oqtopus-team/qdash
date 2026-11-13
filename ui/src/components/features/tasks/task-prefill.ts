import type { TaskInfo, TaskResultResponse } from "@/schemas";
import {
  formatTaskParameter,
  isCompatibleValueType,
  isSweepFormType,
  isSweepValueType,
  parseTaskParameter,
  type SweepFormType,
} from "@/lib/utils/task-parameters";

export interface TaskPrefill {
  input: Record<string, string>;
  run: Record<string, string>;
  /** The sweep form of each run parameter that declares a generated range. */
  runTypes: Record<string, SweepFormType>;
  skipped: string[];
}

/** Apply historical values only when they fit the current form definition. */
export function buildTaskPrefill(task: TaskInfo, source?: TaskResultResponse): TaskPrefill {
  const skipped: string[] = [];
  const runTypes: Record<string, SweepFormType> = {};
  function values(kind: "input" | "run") {
    const definitions = task[`${kind}_parameters`] ?? {};
    const historical = source?.[`${kind}_parameters`] ?? {};
    const result = Object.fromEntries(
      Object.entries(definitions).map(([name, definition]) => [
        name,
        kind === "run" ? formatTaskParameter(definition.value) : "",
      ]),
    );
    if (kind === "run") {
      for (const [name, definition] of Object.entries(definitions)) {
        if (isSweepValueType(definition.value_type)) runTypes[name] = definition.value_type;
      }
    }
    for (const [name, entry] of Object.entries(historical)) {
      const definition = definitions[name];
      const metadata =
        entry !== null && typeof entry === "object" && "value" in entry
          ? (entry as Record<string, unknown>)
          : { value: entry };
      const value = metadata.value;
      const normalizeType = (type: unknown) => (type === "string" ? "str" : type);
      // A sweep parameter restores the form it ran in; other types must match.
      const sweepForm =
        kind === "run" &&
        definition &&
        isSweepValueType(definition.value_type) &&
        isSweepFormType(metadata.value_type)
          ? metadata.value_type
          : null;
      const typeMismatch =
        sweepForm === null &&
        Boolean(metadata.value_type) &&
        Boolean(definition?.value_type) &&
        normalizeType(metadata.value_type) !== normalizeType(definition?.value_type);
      const incompatible =
        !definition ||
        definition.user_override === "forbidden" ||
        !isCompatibleValueType(definition.value_type, metadata.value_type) ||
        typeMismatch ||
        (metadata.unit && definition.unit && metadata.unit !== definition.unit);
      if (incompatible || value === null || value === undefined) {
        skipped.push(`${kind}.${name}`);
        continue;
      }
      try {
        const formatted = formatTaskParameter(value);
        const parsed = parseTaskParameter(formatted, sweepForm ?? definition.value_type);
        // Do not silently convert historical strings, booleans, or objects to another type.
        if (JSON.stringify(parsed) !== JSON.stringify(value)) throw new Error("Incompatible value");
        result[name] = formatted;
        if (sweepForm !== null) runTypes[name] = sweepForm;
      } catch {
        skipped.push(`${kind}.${name}`);
      }
    }
    return result;
  }
  const input = values("input");
  const run = values("run");
  return { input, run, runTypes, skipped };
}
