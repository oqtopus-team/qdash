import type { TaskInfo, TaskResultResponse } from "@/schemas";
import { formatTaskParameter, parseTaskParameter } from "@/lib/utils/task-parameters";

/** Apply historical values only when they fit the current form definition. */
export function buildTaskPrefill(task: TaskInfo, source?: TaskResultResponse) {
  const skipped: string[] = [];
  function values(kind: "input" | "run") {
    const definitions = task[`${kind}_parameters`] ?? {};
    const historical = source?.[`${kind}_parameters`] ?? {};
    const result = Object.fromEntries(
      Object.entries(definitions).map(([name, definition]) => [
        name,
        kind === "run" ? formatTaskParameter(definition.value) : "",
      ]),
    );
    for (const [name, entry] of Object.entries(historical)) {
      const definition = definitions[name];
      const metadata =
        entry !== null && typeof entry === "object" && "value" in entry
          ? (entry as Record<string, unknown>)
          : { value: entry };
      const value = metadata.value;
      const normalizeType = (type: unknown) => (type === "string" ? "str" : type);
      const incompatible =
        !definition ||
        definition.user_override === "forbidden" ||
        (metadata.value_type &&
          definition.value_type &&
          normalizeType(metadata.value_type) !== normalizeType(definition.value_type)) ||
        (metadata.unit && definition.unit && metadata.unit !== definition.unit);
      if (incompatible || value === null || value === undefined) {
        skipped.push(`${kind}.${name}`);
        continue;
      }
      try {
        const formatted = formatTaskParameter(value);
        const parsed = parseTaskParameter(formatted, definition.value_type);
        // Do not silently convert historical strings, booleans, or objects to another type.
        if (JSON.stringify(parsed) !== JSON.stringify(value)) throw new Error("Incompatible value");
        result[name] = formatted;
      } catch {
        skipped.push(`${kind}.${name}`);
      }
    }
    return result;
  }
  const input = values("input");
  const run = values("run");
  return { input, run, skipped };
}
