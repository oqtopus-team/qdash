import type { FlowTemplate } from "@/schemas";

/**
 * Template the New Flow editor opens with: "simple" when the backend ships it, otherwise the
 * first template listed for that backend, or null when the backend has none.
 */
export function pickDefaultTemplate(templates: readonly FlowTemplate[]): FlowTemplate | null {
  return templates.find((template) => template.id === "simple") ?? templates[0] ?? null;
}
