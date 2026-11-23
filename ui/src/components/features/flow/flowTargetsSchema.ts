import { z } from "zod";

import type { FlowTargetOverride } from "@/schemas";

/** Target types the execute dialog can override: MUX IDs, qubit IDs, or coupling pairs. */
const targetModeSchema = z.enum(["mux", "qubit", "pairs"]);

export type TargetMode = z.infer<typeof targetModeSchema>;

/** Splits IDs separated by commas, spaces, or new lines; blank input gives no IDs. */
function splitIds(value: string): string[] {
  const trimmed = value.trim();
  return trimmed ? trimmed.split(/[\s,]+/) : [];
}

/** Parses `control-target` pairs such as `63-85`; returns null when any entry is malformed. */
function parsePairs(value: string): string[][] | null {
  const pairs: string[][] = [];
  for (const token of splitIds(value)) {
    const match = /^(\d+)-(\d+)$/.exec(token);
    if (!match) return null;
    pairs.push([match[1], match[2]]);
  }
  return pairs;
}

/** Returns whether the list holds the same key twice. */
function hasDuplicates(keys: Array<string | number>): boolean {
  return new Set(keys).size !== keys.length;
}

/** Returns the first problem with coupling pair input, or null when the pairs are valid. */
function pairsError(ids: string): string | null {
  const pairs = parsePairs(ids);
  if (pairs === null) {
    return "Use control-target pairs such as 63-85, separated by commas, spaces or new lines.";
  }
  if (!pairs.length) return "Enter at least one coupling pair.";
  if (pairs.some(([control, target]) => control === target)) {
    return "Each pair needs two different qubits.";
  }
  if (hasDuplicates(pairs.map((pair) => pair.join("-")))) return "Remove duplicate coupling pairs.";
  return null;
}

/** Returns the first problem with MUX or qubit ID input, or null when the IDs are valid. */
function idsError(mode: "mux" | "qubit", ids: string, excluded: string): string | null {
  const selected = splitIds(ids);
  const exclusions = mode === "mux" ? splitIds(excluded) : [];
  if (!selected.length) return "Enter at least one target ID.";
  if (
    [...selected, ...exclusions].some((id) => !/^\d+$/.test(id)) ||
    (mode === "mux" && selected.some((id) => !Number.isSafeInteger(Number(id))))
  ) {
    return "Use non-negative integer IDs separated by commas or spaces.";
  }
  if (
    hasDuplicates(mode === "mux" ? selected.map(Number) : selected) ||
    hasDuplicates(exclusions)
  ) {
    return "Remove duplicate target IDs.";
  }
  return null;
}

const flowTargetsInputSchema = z.object({
  mode: targetModeSchema,
  ids: z.string(),
  excluded: z.string(),
});

/** Builds the override a valid target input submits. */
function toOverride({
  mode,
  ids,
  excluded,
}: z.infer<typeof flowTargetsInputSchema>): FlowTargetOverride {
  if (mode === "pairs") return { coupling_pairs: parsePairs(ids) ?? [] };
  if (mode === "qubit") return { qids: splitIds(ids) };
  return { mux_ids: splitIds(ids).map(Number), exclude_qids: splitIds(excluded) };
}

/**
 * Calibration targets entered in the execute dialog. Each input reports at most one message on
 * `ids`; valid input becomes the `FlowTargetOverride` of the run. MUX IDs are compared and
 * submitted as numbers, so `1` and `01` are duplicates; qubit IDs, exclusions, and pair qubits
 * keep their written strings. Exclusions only apply to MUX targets.
 */
export const flowTargetsSchema = flowTargetsInputSchema
  .superRefine(({ mode, ids, excluded }, ctx) => {
    const message = mode === "pairs" ? pairsError(ids) : idsError(mode, ids, excluded);
    if (message) ctx.addIssue({ code: "custom", path: ["ids"], message });
  })
  .transform(toOverride);

export type FlowTargetsFormInput = z.input<typeof flowTargetsSchema>;
export type FlowTargetsFormData = z.output<typeof flowTargetsSchema>;
