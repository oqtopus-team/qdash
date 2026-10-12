"use client";

import { ArrowLeft, XCircle } from "lucide-react";
import { useRouter } from "next/navigation";

import { useGetEvaluationRun } from "@/client/evaluation/evaluation";
import { PageContainer } from "@/components/ui/PageContainer";
import { formatDateTime } from "@/lib/utils/datetime";

import { EvaluationCard } from "./EvaluationCard";
import {
  agreementRate,
  evaluatorLabel,
  modeLabel,
  runDone,
  runIsActive,
  triggerLabel,
} from "./evaluationDisplay";

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <div className="text-xs uppercase text-base-content/50">{label}</div>
      <div className="mt-1 text-sm">{value}</div>
    </div>
  );
}

/** One evaluation run: its progress, what judged it, and every record with verdict controls. */
export function EvaluationRunDetailPageContent({ runId }: { runId: string }) {
  const router = useRouter();
  const goBack = () => router.push("/evaluations");
  const {
    data: response,
    isLoading,
    isError,
  } = useGetEvaluationRun(runId, {
    query: {
      refetchInterval: (query) => {
        const run = query.state.data?.data.run;
        return run && runIsActive(run) ? 5_000 : false;
      },
    },
  });
  const data = response?.data;

  if (isLoading) {
    return (
      <PageContainer maxWidth>
        <div className="flex justify-center py-16">
          <span className="loading loading-spinner loading-lg" />
        </div>
      </PageContainer>
    );
  }

  if (isError || !data) {
    return (
      <PageContainer maxWidth>
        <div className="mb-6 flex items-center gap-3">
          <button className="btn btn-square btn-ghost btn-sm shrink-0" onClick={goBack}>
            <ArrowLeft className="h-4 w-4" />
          </button>
          <h1 className="text-xl font-bold">AI Evaluation</h1>
        </div>
        <div className="alert alert-error">
          <XCircle className="h-5 w-5" />
          <span>Failed to load this evaluation run.</span>
        </div>
      </PageContainer>
    );
  }

  const { run, evaluations } = data;
  const agreement = agreementRate(run);

  return (
    <PageContainer maxWidth>
      <div className="mb-6 flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <button className="btn btn-square btn-ghost btn-sm shrink-0" onClick={goBack}>
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div className="min-w-0">
            <h1 className="truncate text-xl font-bold">
              {run.task_name} · {run.chip_id}
            </h1>
            <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-base-content/50">
              <span className="badge badge-neutral badge-sm">{run.entity_type}</span>
              <span className="badge badge-outline badge-sm">{triggerLabel(run.trigger)}</span>
              <span className="badge badge-outline badge-sm">{modeLabel(run.mode)}</span>
              {run.date && <span>{run.date}</span>}
              <span>requested {formatDateTime(run.requested_at)}</span>
              <span>by {run.requested_by}</span>
              <span className="font-mono">{run.run_id}</span>
            </div>
          </div>
        </div>
        <div className="flex flex-shrink-0 flex-wrap gap-2">
          {runIsActive(run) && <span className="badge badge-info">running</span>}
          <span className="badge badge-neutral">
            {runDone(run)}/{run.total} done
          </span>
          {run.failed_count > 0 && (
            <span className="badge badge-error">{run.failed_count} failed</span>
          )}
        </div>
      </div>

      <div className="mb-4 rounded-lg border border-base-300 bg-base-100 p-4">
        <div className="grid gap-3 md:grid-cols-6">
          <Stat label="Success" value={`${run.success_count}/${run.completed_count}`} />
          <Stat label="Parsed as JSON" value={`${run.parsed_count}/${run.completed_count}`} />
          <Stat
            label="Agreement"
            value={
              agreement === null
                ? "not judged yet"
                : `${Math.round(agreement * 100)}% of ${run.agree_count + run.disagree_count}`
            }
          />
          <Stat label="Evaluation model" value={run.model || "-"} />
          <Stat label="Evaluator" value={evaluatorLabel(run.evaluator) || "-"} />
          <Stat
            label={run.mode === "planner" ? "Planner" : "Mode"}
            value={run.mode === "planner" ? run.planner_model || "-" : "direct tools"}
          />
        </div>
        {run.question && (
          <div className="mt-3 text-sm">
            <span className="text-xs uppercase text-base-content/50">Question</span>
            <p className="mt-1 text-base-content/80">{run.question}</p>
          </div>
        )}
      </div>

      <div className="space-y-4">
        {evaluations.map((item) => (
          <EvaluationCard key={item.evaluation_id} item={item} />
        ))}
      </div>
    </PageContainer>
  );
}
