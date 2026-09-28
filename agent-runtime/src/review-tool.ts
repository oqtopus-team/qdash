import { defineTool } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

/**
 * The only tool an AI review session gets.
 *
 * Pi has no way to constrain assistant text to a JSON schema, so the verdict is
 * collected as tool arguments instead. `constrainedSampling` hands the schema to
 * the provider's constrained decoder; "prefer" falls back to an ordinary tool
 * call when the provider does not support it rather than failing the request.
 *
 * The fields mirror the markdown block QDash stores, one for one. Rendering
 * stays in Python so the saved note keeps its existing format.
 * See .agents/sessions/2026-09-28-ai-review-pi-agent/adr/0002-*.md
 */
export const submitReviewTool = defineTool({
  name: "submit_review",
  label: "Submit review",
  description:
    "Submit the final calibration review verdict. Call this exactly once, as your last action. " +
    "Do not write the verdict as prose; every field belongs in this call.",
  constrainedSampling: { type: "json_schema", strict: "prefer" },
  parameters: Type.Object({
    decision: Type.Union(
      [
        Type.Literal("PASS"),
        Type.Literal("PASS_WITH_NOTE"),
        Type.Literal("REVIEW"),
        Type.Literal("FAIL"),
      ],
      { description: "Whether this result is safe for routine parameter update." },
    ),
    human_label: Type.Union(
      [
        Type.Literal("CORRECT"),
        Type.Literal("SUSPICIOUS"),
        Type.Literal("MISASSIGNMENT"),
        Type.Literal("NO_SIGNAL"),
        Type.Literal("ANOMALY"),
      ],
      { description: "The label a human reviewer would most likely assign." },
    ),
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
  execute: async (_toolCallId, params) => ({
    content: [{ type: "text" as const, text: "Review recorded." }],
    details: { review: params },
  }),
});
