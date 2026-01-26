"use client";

import { useMemo } from "react";
import { useRouter } from "next/navigation";
import { Copy, Wand2 } from "lucide-react";

import {
  useGetProvenanceEntity,
  useGetRecalibrationRecommendations,
} from "@/client/provenance/provenance";
import { useToast } from "@/components/ui/Toast";

interface RecalibrationRecommendationsPanelProps {
  entityId: string;
  maxDepth?: number;
}

export function RecalibrationRecommendationsPanel({
  entityId,
  maxDepth = 10,
}: RecalibrationRecommendationsPanelProps) {
  const router = useRouter();
  const toast = useToast();

  const { data: entityResp } = useGetProvenanceEntity(entityId, {
    query: { enabled: !!entityId },
  });
  const entity = entityResp?.data;

  const { data, isLoading, isError } = useGetRecalibrationRecommendations(
    entityId,
    { max_depth: maxDepth },
    { query: { enabled: !!entityId } },
  );

  const rec = data?.data;
  const tasks = useMemo(() => rec?.recommended_tasks ?? [], [rec]);

  const tasksSnippet = useMemo(() => {
    const taskNames = tasks.map((t) => t.task_name);
    return JSON.stringify(taskNames, null, 2);
  }, [tasks]);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(tasksSnippet);
      toast.success("Copied tasks list to clipboard");
    } catch {
      toast.error("Failed to copy to clipboard");
    }
  };

  return (
    <div className="card bg-base-200">
      <div className="card-body p-4 sm:p-6">
        <div className="flex items-center justify-between gap-3">
          <h3 className="card-title text-base sm:text-lg">
            Suggested Next Actions
          </h3>
          <div className="flex items-center gap-2">
            <button
              className="btn btn-xs btn-ghost"
              onClick={handleCopy}
              disabled={tasks.length === 0}
              title="Copy as tasks list"
            >
              <Copy className="h-4 w-4" />
            </button>
            <button
              className="btn btn-xs btn-ghost"
              onClick={() => router.push("/workflow/new")}
              title="Open Flow Editor"
            >
              <Wand2 className="h-4 w-4" />
            </button>
          </div>
        </div>

        <p className="text-sm text-base-content/70">
          Use this list as a runbook: re-run higher priority tasks first to
          restore downstream parameter consistency.
        </p>

        {entity && (
          <div className="text-xs text-base-content/70">
            <span className="badge badge-outline badge-sm mr-2">
              {entity.parameter_name} ({entity.qid})
            </span>
            <span className="font-mono">
              {typeof entity.value === "number"
                ? entity.value.toExponential(4)
                : String(entity.value)}{" "}
              {entity.unit || ""}
            </span>
            {entity.error && entity.error !== 0 && (
              <span className="ml-2 text-warning font-mono" title="error">
                ±{entity.error.toExponential(2)}
              </span>
            )}
          </div>
        )}

        {isLoading && (
          <div className="flex items-center gap-2 py-2">
            <span className="loading loading-spinner loading-sm"></span>
            <span className="text-sm text-base-content/60">
              Computing recommendations...
            </span>
          </div>
        )}

        {isError && (
          <div className="alert alert-warning">
            <span>Failed to load recalibration recommendations</span>
          </div>
        )}

        {!isLoading && !isError && rec && (
          <div className="space-y-3">
            <div className="flex flex-wrap gap-2 text-xs text-base-content/70">
              <span className="badge badge-outline">
                affected: {rec.total_affected_parameters ?? 0}
              </span>
              <span className="badge badge-outline">
                depth: {rec.max_depth_reached ?? 0}
              </span>
              {rec.source_parameter_name && rec.source_qid && (
                <span className="badge badge-primary">
                  {rec.source_parameter_name} ({rec.source_qid})
                </span>
              )}
            </div>

            {tasks.length === 0 ? (
              <div className="text-sm text-base-content/60">
                No downstream tasks found for this parameter.
              </div>
            ) : (
              <div className="space-y-2">
                {tasks.map((t) => (
                  <details
                    key={`${t.priority}:${t.task_name}`}
                    className="collapse collapse-arrow bg-base-100/50"
                  >
                    <summary className="collapse-title py-2">
                      <div className="flex items-center justify-between gap-3">
                        <div className="flex items-center gap-2 min-w-0">
                          <span className="badge badge-primary badge-sm">
                            P{t.priority}
                          </span>
                          <span className="font-medium truncate">
                            {t.task_name}
                          </span>
                        </div>
                        <div className="hidden sm:flex flex-wrap gap-1 justify-end">
                          <span className="badge badge-outline badge-sm">
                            params: {(t.affected_parameters ?? []).length}
                          </span>
                          <span className="badge badge-outline badge-sm">
                            qids: {(t.affected_qids ?? []).length}
                          </span>
                        </div>
                      </div>
                    </summary>
                    <div className="collapse-content">
                      <div className="text-sm text-base-content/70">
                        {t.reason || "-"}
                      </div>
                      <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-3">
                        <div>
                          <div className="text-xs font-medium text-base-content/60 mb-1">
                            Affected parameters
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {(t.affected_parameters ?? []).length === 0 ? (
                              <span className="text-xs text-base-content/50">
                                -
                              </span>
                            ) : (
                              (t.affected_parameters ?? [])
                                .slice(0, 20)
                                .map((p) => (
                                  <span
                                    key={p}
                                    className="badge badge-outline badge-sm"
                                  >
                                    {p}
                                  </span>
                                ))
                            )}
                            {(t.affected_parameters ?? []).length > 20 && (
                              <span className="badge badge-outline badge-sm">
                                +{(t.affected_parameters ?? []).length - 20}
                              </span>
                            )}
                          </div>
                        </div>
                        <div>
                          <div className="text-xs font-medium text-base-content/60 mb-1">
                            Affected QIDs
                          </div>
                          <div className="flex flex-wrap gap-1">
                            {(t.affected_qids ?? []).length === 0 ? (
                              <span className="text-xs text-base-content/50">
                                -
                              </span>
                            ) : (
                              (t.affected_qids ?? []).slice(0, 20).map((q) => (
                                <span
                                  key={q}
                                  className="badge badge-outline badge-sm"
                                >
                                  {q}
                                </span>
                              ))
                            )}
                            {(t.affected_qids ?? []).length > 20 && (
                              <span className="badge badge-outline badge-sm">
                                +{(t.affected_qids ?? []).length - 20}
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  </details>
                ))}
              </div>
            )}

            {tasks.length > 0 && (
              <details className="collapse collapse-arrow bg-base-100/50">
                <summary className="collapse-title text-sm font-medium">
                  Copyable tasks list
                </summary>
                <div className="collapse-content">
                  <pre className="text-xs bg-base-100 rounded p-3 overflow-auto">
                    {tasksSnippet}
                  </pre>
                </div>
              </details>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
