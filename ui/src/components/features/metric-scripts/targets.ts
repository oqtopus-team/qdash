import type { MetricInfo } from "@/schemas";

/** Most qubits or directed pairs a series metric evaluates and draws; the API enforces it. */
export const MAX_SERIES_TARGETS = 16;

/** Whether a metric returns a time series per selected target instead of one value. */
export function isSeriesMetric(metric: Pick<MetricInfo, "result"> | null | undefined): boolean {
  return metric?.result === "series";
}

function qubit(text: string): string | null {
  const digits = text.trim().replace(/^Q/i, "");
  return /^\d+$/.test(digits) ? String(Number.parseInt(digits, 10)) : null;
}

/**
 * Parse typed targets ("0>1, 1-2" or "Q05 6") into cell keys: "5" for a qubit, "5>6" for a
 * directed pair. The direction of a pair is kept. Mirrors the API's `normalize_target_key`;
 * the server still checks the targets against the chip.
 */
export function parseTargets(
  text: string,
  target: MetricInfo["target"] | undefined,
): { keys: string[]; error: string | null } {
  const items = text
    .split(/[\s,]+/)
    .map((item) => item.trim())
    .filter(Boolean);
  const keys: string[] = [];
  for (const item of items) {
    const ends = item.replace(">", "-").split("-");
    let key: string | null = null;
    if (ends.length === 2 && target !== "qubit") {
      const [source, sink] = [qubit(ends[0]), qubit(ends[1])];
      key = source !== null && sink !== null ? `${source}>${sink}` : null;
    } else if (ends.length === 1 && target !== "pair") {
      key = qubit(ends[0]);
    }
    if (key === null) {
      const expected = target === "qubit" ? "a qubit ID such as 5" : "a directed pair such as 0>1";
      return { keys, error: `“${item}” is not ${expected}` };
    }
    if (keys.includes(key)) return { keys, error: `${formatTarget(key)} is listed twice` };
    keys.push(key);
  }
  if (keys.length === 0) {
    return { keys, error: `Select 1 to ${MAX_SERIES_TARGETS} ${targetNoun(target)}` };
  }
  if (keys.length > MAX_SERIES_TARGETS) {
    return { keys, error: `Select at most ${MAX_SERIES_TARGETS} ${targetNoun(target)}` };
  }
  return { keys, error: null };
}

function targetNoun(target: MetricInfo["target"] | undefined): string {
  return target === "qubit" ? "qubits" : "directed pairs";
}

/** The typed form of stored targets, for an input field. */
export function targetsText(keys: readonly string[]): string {
  return keys.join(", ");
}

/** "Q5" for a qubit key, "Q0 → Q1" for a directed pair key, as `cellName` writes cells. */
export function formatTarget(key: string): string {
  const [source, sink] = key.split(">");
  return sink === undefined ? `Q${source}` : `Q${source} → Q${sink}`;
}
