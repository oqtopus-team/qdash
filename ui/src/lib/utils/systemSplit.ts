import { getApiErrorMessage } from "./apiError";

const SYSTEM_SPLIT_CODE = "system_split_required";

export interface SystemSplit {
  message: string;
  chipId: string | null;
  /** System ID to the targets that fall on it. */
  systems: Record<string, string[]>;
}

/**
 * The split detail of a run refused because its targets span Qubex Systems.
 * The API answers 400 with `{message, code: "system_split_required", chip_id, systems}`.
 */
export function getSystemSplit(error: unknown): SystemSplit | null {
  const detail = (error as { response?: { data?: { detail?: unknown } } } | null)?.response?.data
    ?.detail;
  if (!detail || typeof detail !== "object" || Array.isArray(detail)) return null;
  const record = detail as Record<string, unknown>;
  if (record.code !== SYSTEM_SPLIT_CODE) return null;
  const systems: Record<string, string[]> = {};
  const rawSystems = record.systems;
  if (rawSystems && typeof rawSystems === "object") {
    for (const [systemId, qids] of Object.entries(rawSystems as Record<string, unknown>)) {
      systems[systemId] = Array.isArray(qids) ? qids.map((qid) => String(qid)) : [];
    }
  }
  return {
    message: typeof record.message === "string" ? record.message : "",
    chipId: typeof record.chip_id === "string" ? record.chip_id : null,
    systems,
  };
}

/** One line per System, followed by what to do about it. */
export function formatSystemSplit(split: SystemSplit): string {
  const lines = Object.entries(split.systems).map(
    ([systemId, qids]) => `${systemId}: ${qids.join(", ") || "no targets"}`,
  );
  return [
    "The targets span more than one System, and a run drives one System at a time.",
    ...lines,
    "Run one System at a time.",
  ].join("\n");
}

/** The split explanation when the error is one, else the ordinary API message. */
export function getRunErrorMessage(error: unknown, fallback: string): string {
  const split = getSystemSplit(error);
  return split ? formatSystemSplit(split) : getApiErrorMessage(error, fallback);
}
