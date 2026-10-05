import { defineTool } from "@earendil-works/pi-durable";
import { Type } from "typebox";

const DECISIONS = ["PASS", "PASS_WITH_NOTE", "REVIEW", "FAIL"];
const HUMAN_LABELS = ["CORRECT", "SUSPICIOUS", "MISASSIGNMENT", "NO_SIGNAL", "ANOMALY"];

/**
 * Map a model's answer onto a closed set, falling back instead of rejecting.
 *
 * The schema deliberately declares these fields as plain strings. Declaring
 * `enum` would make pi's validateToolArguments() throw on a near-miss like
 * "accepted", the agent would retry, and the review would burn its whole
 * timeout without producing a verdict (observed with vLLM 0.21 + Gemma-4-31B).
 * Absorbing the near-miss here keeps the verdict model-independent.
 */
function pick(value: unknown, allowed: string[], fallback: string): string {
  const normalized = String(value ?? "")
    .trim()
    .toUpperCase()
    .replace(/[\s-]+/g, "_");
  return allowed.includes(normalized) ? normalized : fallback;
}

function oneLine(value: unknown): string {
  return String(value ?? "").replace(/\s+/g, " ").trim();
}

/**
 * Normalize a verdict so downstream consumers only ever see the closed sets.
 *
 * Unrecognised values fall back to human review rather than to a pass: an
 * unreadable verdict must never route a calibration result into automatic
 * parameter update.
 */
export function normalizeVerdict(params: Record<string, unknown>): Record<string, string> {
  return {
    decision: pick(params.decision, DECISIONS, "REVIEW"),
    human_label: pick(params.human_label, HUMAN_LABELS, "SUSPICIOUS"),
    accepted_parameters: oneLine(params.accepted_parameters),
    needs_review: oneLine(params.needs_review),
    primary_reason: oneLine(params.primary_reason),
    closest_knowledge_case: oneLine(params.closest_knowledge_case),
    suggested_labels: oneLine(params.suggested_labels),
    recommended_action: oneLine(params.recommended_action),
    optional_note: oneLine(params.optional_note),
  };
}

/**
 * The only tool an AI review session gets.
 *
 * Pi has no way to constrain assistant text to a JSON schema, so the verdict is
 * collected as tool arguments instead. The schema is sent to the provider as
 * ordinary tool parameters; provider-side constrained decoding is deliberately
 * not requested. Anthropic's grammar compiler (used by both Bedrock and the
 * direct API) rejects this schema as too large, and asking for it would tie the
 * review to whichever providers happen to accept it.
 *
 * The fields mirror the markdown block QDash stores, one for one. Rendering
 * stays in Python so the saved note keeps its existing format.
 */
export const submitReviewTool = defineTool({
  name: "submit_review",
  description:
    "Submit the final calibration review verdict. Call this exactly once, as your last action. " +
    "Do not write the verdict as prose; every field belongs in this call.",
  parameters: Type.Object({
    decision: Type.String({
      description:
        "Whether this result is safe for routine parameter update. " +
        "One of: PASS, PASS_WITH_NOTE, REVIEW, FAIL.",
    }),
    human_label: Type.String({
      description:
        "The label a human reviewer would most likely assign. " +
        "One of: CORRECT, SUSPICIOUS, MISASSIGNMENT, NO_SIGNAL, ANOMALY.",
    }),
    accepted_parameters: Type.String({
      description: "Output parameters that can be accepted, or `none`.",
    }),
    needs_review: Type.String({
      description: "Output parameters that need human review, or `none`.",
    }),
    primary_reason: Type.String({ description: "One or two sentences behind the decision." }),
    closest_knowledge_case: Type.String({
      description: "Closest matching case from the task knowledge, or `none`.",
    }),
    suggested_labels: Type.String({ description: "Comma-separated labels for this result." }),
    recommended_action: Type.String({ description: "What the operator should do next." }),
    optional_note: Type.String({ description: "Any remaining caveat, or an empty string." }),
  }),
  replay: "safe",
  execute: async (params) => ({
    content: [{ type: "text" as const, text: "Review recorded." }],
    details: { review: normalizeVerdict(params) },
    // The verdict is the whole point of the session; without this the agent
    // takes another turn and calls the tool again.
    control: { terminate: true },
  }),
});
