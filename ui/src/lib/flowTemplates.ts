import type { FlowTemplate } from "@/schemas";

/**
 * Template the New Flow editor opens with: the requested template when the backend lists it,
 * otherwise "simple" when the backend ships it, otherwise the first template listed for that
 * backend, or null when the backend has none.
 */
export function pickDefaultTemplate(
  templates: readonly FlowTemplate[],
  requestedId?: string | null,
): FlowTemplate | null {
  return (
    (requestedId ? templates.find((template) => template.id === requestedId) : undefined) ??
    templates.find((template) => template.id === "simple") ??
    templates[0] ??
    null
  );
}

/** New Flow editor opened on one backend's template, e.g. after creating a preset chip. */
export function newFlowTemplateHref(backend: string, templateId: string, chipId?: string): string {
  const params = new URLSearchParams({ backend, template: templateId });
  if (chipId) params.set("chip_id", chipId);
  return `/workflow/new?${params.toString()}`;
}
