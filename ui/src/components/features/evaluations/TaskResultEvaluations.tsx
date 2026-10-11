"use client";

import { Bot } from "lucide-react";
import { useState } from "react";

import { useListEvaluations } from "@/client/evaluation/evaluation";
import { useProject } from "@/contexts/ProjectContext";

import { EvaluationCard } from "./EvaluationCard";
import { EvaluationRequestModal } from "./EvaluationRequestModal";

interface TaskResultEvaluationsProps {
  taskId: string;
  chipId: string | null | undefined;
  taskName: string;
  qid: string;
}

/**
 * The AI evaluations of one task result, newest first, with a button to
 * request another. A single result's evaluation takes the same path and leaves
 * the same record as a bulk run from the chip page.
 */
export function TaskResultEvaluations({
  taskId,
  chipId,
  taskName,
  qid,
}: TaskResultEvaluationsProps) {
  const { canEdit } = useProject();
  const [isRequestOpen, setIsRequestOpen] = useState(false);
  const { data: response } = useListEvaluations(
    { task_id: taskId },
    {
      query: {
        enabled: !!taskId,
        refetchInterval: (query) =>
          query.state.data?.data.evaluations.some(
            (item) => item.status === "pending" || item.status === "running",
          )
            ? 5_000
            : false,
      },
    },
  );
  const evaluations = response?.data.evaluations ?? [];

  return (
    <section className="mb-6">
      <div className="mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Bot className="h-4 w-4 text-primary" />
          AI evaluation
          {evaluations.length > 0 && (
            <span className="badge badge-ghost badge-sm">{evaluations.length}</span>
          )}
        </div>
        {canEdit && (
          <button
            type="button"
            className="btn btn-sm btn-outline gap-1"
            onClick={() => setIsRequestOpen(true)}
            disabled={!chipId}
            title={
              chipId ? "Evaluate this result with the calibration evaluation model" : "No chip"
            }
          >
            <Bot className="h-4 w-4" />
            Evaluate
          </button>
        )}
      </div>
      {evaluations.length === 0 ? (
        <p className="text-sm text-base-content/50">
          No AI evaluation yet. Evaluate sends the figure and the task&apos;s reference to the
          calibration evaluation model and keeps the record here.
        </p>
      ) : (
        <div className="space-y-3">
          {evaluations.map((item) => (
            <EvaluationCard
              key={item.evaluation_id}
              item={item}
              showFigure={false}
              showTarget={false}
              showRunLink
            />
          ))}
        </div>
      )}
      {chipId && (
        <EvaluationRequestModal
          isOpen={isRequestOpen}
          onClose={() => setIsRequestOpen(false)}
          scope={{
            chipId,
            taskName,
            entityType: qid.includes("-") ? "coupling" : "qubit",
            taskIds: [taskId],
            trigger: "single",
          }}
          scopeLabel={`${taskName} · ${qid}`}
        />
      )}
    </section>
  );
}
