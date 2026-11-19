import type { MetricScriptResponse } from "@/schemas";

export const SOURCE = `from qdash_metrics import metric


@metric(title="T1", unit="us")
def t1(target, ctx):
    return ctx.data["t1"][target].latest()
`;

export function scriptResponse(
  overrides: Partial<MetricScriptResponse> = {},
): MetricScriptResponse {
  return {
    script_id: "ms_000000000001",
    project_id: "project-1",
    name: "Coherence",
    description: "T1 per qubit",
    visibility: "private",
    status: "valid",
    revision: 3,
    active_revision: 3,
    metrics: [
      {
        id: "t1",
        title: "T1",
        unit: "us",
        target: "qubit",
        hops: [1, 2],
        parameters: {},
        has_legend: false,
      },
    ],
    template_id: null,
    owner_username: "alice",
    owner_user_id: "user-alice",
    can_edit: true,
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-02T00:00:00Z",
    source: SOURCE,
    active_source: SOURCE,
    diagnostics: [],
    revisions: [],
    ...overrides,
  };
}
