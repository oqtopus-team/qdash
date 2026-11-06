import type { EvaluationInputModel, EvaluationItem } from "@/schemas";

/**
 * What an evaluation's prompt was made of, read off the stored record, so a
 * person can tell later what the evaluation model was given without opening
 * the full text: the system prompt, the host-supplied reference (task
 * knowledge), labeled examples, the figures, and a question.
 */

/** Short digest of a hash for display. */
function shortSha(sha256: string | null | undefined): string | null {
  return sha256 ? sha256.slice(0, 8) : null;
}

/** One line: what the user turn contained, in the order the model received it. */
export function promptSummary(
  input: Pick<
    EvaluationInputModel,
    "system_prompt" | "knowledge_chars" | "examples" | "figures" | "question"
  >,
): string {
  const parts: string[] = [];
  parts.push(input.system_prompt ? "system prompt" : "system prompt not recorded");
  parts.push(input.knowledge_chars ? `reference ${input.knowledge_chars} chars` : "no reference");
  const examples = input.examples?.length ?? 0;
  if (examples > 0) parts.push(`${examples} labeled example${examples === 1 ? "" : "s"}`);
  const figures = input.figures?.length ?? 0;
  parts.push(`${figures} figure${figures === 1 ? "" : "s"}`);
  if (input.question) parts.push("question");
  return parts.join(" · ");
}

/** The prompt ingredients across the evaluations of one run, and whether they varied. */
export interface PromptProfile {
  /** Evaluations whose input was recorded. */
  recorded: number;
  /** The system prompt, when every recorded evaluation had the same one. */
  systemPrompt: string | null;
  /** Distinct system prompts seen, counting "not recorded" as one when it occurred. */
  systemPromptVariants: number;
  /** Each distinct system prompt seen ("" for not recorded), sorted, for comparing runs. */
  systemPromptValues: string[];
  /** The reference, when every recorded evaluation had the same one; sha256 is null when unknown. */
  reference: { chars: number | null; sha256: string | null } | null;
  /** Distinct references seen, counting "none" as one when it occurred. */
  referenceVariants: number;
  /** Identity of each distinct reference seen ("" for none), sorted, for comparing runs. */
  referenceKeys: string[];
  examples: { min: number; max: number };
  figures: { min: number; max: number };
  /** The question asked, when every recorded evaluation had the same one. */
  question: string | null;
  /** Distinct questions seen, counting "no question" as one when it occurred. */
  questionVariants: number;
}

/** The smallest and largest of the values, or zeros when there are none. */
function range(values: number[]): { min: number; max: number } {
  if (values.length === 0) return { min: 0, max: 0 };
  return { min: Math.min(...values), max: Math.max(...values) };
}

/** Reads the prompt ingredients off the recorded inputs of a run's evaluations. */
export function promptProfile(items: ReadonlyArray<EvaluationItem>): PromptProfile {
  const inputs = items
    .map((item) => item.input)
    .filter((input): input is EvaluationInputModel => !!input);
  const systemPrompts = new Set(inputs.map((input) => input.system_prompt || ""));
  const references = new Map<string, { chars: number | null; sha256: string | null } | null>();
  for (const input of inputs) {
    const chars = input.knowledge_chars ?? null;
    const sha256 = input.knowledge_sha256 || null;
    if (sha256 || chars) {
      references.set(sha256 ?? `unknown:${chars}`, { chars, sha256 });
    } else {
      references.set("", null);
    }
  }
  const questions = new Set(inputs.map((input) => input.question || ""));
  const only = <T>(set: Set<T>): T | null => (set.size === 1 ? [...set][0] : null);
  return {
    recorded: inputs.length,
    systemPrompt: only(systemPrompts) || null,
    systemPromptVariants: systemPrompts.size,
    systemPromptValues: [...systemPrompts].sort(),
    reference: references.size === 1 ? ([...references.values()][0] ?? null) : null,
    referenceVariants: references.size,
    referenceKeys: [...references.keys()].sort(),
    examples: range(inputs.map((input) => input.examples?.length ?? 0)),
    figures: range(inputs.map((input) => input.figures?.length ?? 0)),
    question: only(questions) || null,
    questionVariants: questions.size,
  };
}

/** The reference as one label: its size and hash, "none", or how many were seen. */
export function referenceLabel(profile: PromptProfile): string {
  if (profile.recorded === 0) return "-";
  if (profile.referenceVariants > 1) return `varies (${profile.referenceVariants})`;
  if (!profile.reference) return "none";
  const size =
    profile.reference.chars === null ? "size unknown" : `${profile.reference.chars} chars`;
  return `${size} · ${shortSha(profile.reference.sha256) ?? "hash unknown"}`;
}

/** The system prompt as one label: its size, "not recorded", or how many were seen. */
export function systemPromptLabel(profile: PromptProfile): string {
  if (profile.recorded === 0) return "-";
  if (profile.systemPromptVariants > 1) return `varies (${profile.systemPromptVariants})`;
  if (!profile.systemPrompt) return "not recorded";
  return `${profile.systemPrompt.length} chars`;
}

/** A count range as "2" or "1–3". */
export function rangeLabel({ min, max }: { min: number; max: number }): string {
  return min === max ? `${min}` : `${min}–${max}`;
}
