"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  CheckCircle2,
  Copy,
  ExternalLink,
  Image as ImageIcon,
  XCircle,
} from "lucide-react";

import { useGetTaskResultAiReviewRun } from "@/client/task-result/task-result";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { MarkdownContent } from "@/components/ui/MarkdownContent";
import { PageContainer } from "@/components/ui/PageContainer";
import { useToast } from "@/components/ui/Toast";
import { formatDateTime } from "@/lib/utils/datetime";
import type { AiReviewListItem } from "@/schemas";

function decisionBadgeClass(decision: string, formatOk: boolean): string {
  if (!formatOk || decision === "FORMAT_ERROR") return "badge-error";
  if (decision === "FAIL") return "badge-error";
  if (decision === "REVIEW") return "badge-warning";
  if (decision === "PASS_WITH_NOTE") return "badge-info";
  if (decision === "PASS") return "badge-success";
  return "badge-ghost";
}

function BackButton({ onClick }: { onClick: () => void }) {
  return (
    <button className="btn btn-square btn-ghost btn-sm shrink-0" onClick={onClick}>
      <ArrowLeft className="h-4 w-4" />
    </button>
  );
}

function StatusIcon({ item }: { item: AiReviewListItem }) {
  if (!item.format_ok || item.decision === "FORMAT_ERROR") {
    return <XCircle className="h-4 w-4 text-error" aria-hidden="true" />;
  }
  if (item.decision === "REVIEW" || item.decision === "FAIL") {
    return <AlertTriangle className="h-4 w-4 text-warning" aria-hidden="true" />;
  }
  return <CheckCircle2 className="h-4 w-4 text-success" aria-hidden="true" />;
}

function ReviewCard({ item }: { item: AiReviewListItem }) {
  const toast = useToast();
  const figurePaths = item.figure_path ?? [];
  const jsonFigurePaths = item.json_figure_path ?? [];
  const visibleFigurePaths = figurePaths.length > 0 ? figurePaths : jsonFigurePaths;
  const reviewedAt =
    item.completed_at || item.note_updated_at || item.requested_at || item.start_at;

  const copyPath = async (path: string) => {
    try {
      await navigator.clipboard.writeText(path);
      toast.success("Copied figure path");
    } catch {
      toast.error("Failed to copy figure path");
    }
  };

  return (
    <article className="rounded-lg border border-base-300 bg-base-100 p-4">
      <div className="grid gap-4 xl:grid-cols-[minmax(0,460px)_minmax(0,1fr)]">
        <div className="rounded-lg border border-base-300 bg-base-200/40 p-3">
          {visibleFigurePaths.length > 0 ? (
            <div className="flex gap-3 overflow-x-auto pb-1">
              {visibleFigurePaths.map((path: string, index: number) => {
                const fileName = path.split("/").pop() ?? path;
                return (
                  <div
                    key={`${item.task_id}-${path}-${index}`}
                    className="flex w-[420px] flex-shrink-0 flex-col gap-2"
                  >
                    <div className="flex items-center justify-between gap-2 text-xs text-base-content/50">
                      <span>
                        Figure {index + 1} / {visibleFigurePaths.length}
                      </span>
                      <button
                        type="button"
                        onClick={() => copyPath(path)}
                        className="btn btn-ghost btn-xs gap-1"
                        title={`Copy path: ${path}`}
                      >
                        <Copy className="h-3 w-3" />
                        Copy path
                      </button>
                    </div>
                    {/* White backdrop keeps matplotlib figures legible across themes
                        (same convention as the chip TaskDetailModal figure panel). */}
                    <div className="flex h-[340px] items-center justify-center rounded-lg bg-white p-2">
                      <TaskFigure
                        path={path}
                        jsonFigurePath={jsonFigurePaths[index]}
                        qid={item.qid}
                        className="max-h-full w-auto object-contain"
                      />
                    </div>
                    <div
                      className="truncate font-mono text-[11px] text-base-content/40"
                      title={path}
                    >
                      {fileName}
                    </div>
                  </div>
                );
              })}
            </div>
          ) : (
            <div className="flex h-[340px] flex-col items-center justify-center gap-2 text-sm text-base-content/50">
              <ImageIcon className="h-8 w-8" />
              No figure
            </div>
          )}
        </div>

        <div className="min-w-0">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <StatusIcon item={item} />
            <span className={`badge ${decisionBadgeClass(item.decision, item.format_ok)}`}>
              {item.decision}
            </span>
            {item.human_label && <span className="badge badge-outline">{item.human_label}</span>}
            {item.review_status && <span className="badge badge-ghost">{item.review_status}</span>}
            <Link href={`/task-results/${item.task_id}`} className="btn btn-ghost btn-xs gap-1">
              <ExternalLink className="h-3.5 w-3.5" />
              Result
            </Link>
          </div>
          <div className="mb-3">
            <h2 className="truncate text-base font-semibold">{item.target}</h2>
            <div className="mt-1 flex flex-wrap gap-2 text-xs text-base-content/50">
              <span>{item.task_name}</span>
              <span>{item.chip_id}</span>
              <span>{formatDateTime(reviewedAt)}</span>
              <span className="font-mono">{item.task_id}</span>
            </div>
          </div>

          <div className="grid gap-3 text-sm md:grid-cols-2">
            <div>
              <div className="text-xs uppercase text-base-content/50">Primary reason</div>
              <p className="mt-1 text-base-content/80">{item.primary_reason || "-"}</p>
            </div>
            <div>
              <div className="text-xs uppercase text-base-content/50">Recommended action</div>
              <p className="mt-1 text-base-content/80">{item.recommended_action || "-"}</p>
            </div>
            <div>
              <div className="text-xs uppercase text-base-content/50">Accepted parameters</div>
              <p className="mt-1 text-base-content/80">{item.accepted_parameters || "-"}</p>
            </div>
            <div>
              <div className="text-xs uppercase text-base-content/50">Suggested labels</div>
              <p className="mt-1 text-base-content/80">{item.suggested_labels || "-"}</p>
            </div>
          </div>

          <details className="mt-4">
            <summary className="cursor-pointer text-sm font-medium text-primary">
              Full AI review markdown
            </summary>
            <div className="mt-3 rounded-lg border border-base-300 bg-base-200/40 p-4">
              <MarkdownContent content={item.review_markdown || "No AI review markdown."} />
            </div>
          </details>
        </div>
      </div>
    </article>
  );
}

export function AiReviewRunDetailPageContent({ reviewRunId }: { reviewRunId: string }) {
  const router = useRouter();
  const goBack = () => router.push("/ai-reviews");
  const {
    data: response,
    isLoading,
    isError,
  } = useGetTaskResultAiReviewRun(reviewRunId, {
    query: { staleTime: 15_000 },
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
          <BackButton onClick={goBack} />
          <h1 className="text-xl font-bold">AI Review</h1>
        </div>
        <div className="alert alert-error">
          <XCircle className="h-5 w-5" />
          <span>Failed to load this AI review run.</span>
        </div>
      </PageContainer>
    );
  }

  const run = data.run;
  const done = run.completed_count + run.failed_count;

  return (
    <PageContainer maxWidth>
      <div className="mb-6 flex items-start justify-between gap-4">
        <div className="flex min-w-0 items-start gap-3">
          <BackButton onClick={goBack} />
          <div className="min-w-0">
            <h1 className="truncate text-xl font-bold">{run.task_name} AI Review</h1>
            <div className="mt-1 flex flex-wrap items-center gap-3 text-xs text-base-content/50">
              <span>{run.chip_id}</span>
              <span>requested {formatDateTime(run.requested_at)}</span>
              <span className="font-mono">{run.review_run_id}</span>
            </div>
          </div>
        </div>
        <div className="flex flex-shrink-0 flex-wrap gap-2">
          <span className="badge badge-neutral">
            {done}/{run.total} done
          </span>
          {Object.entries(run.decision_counts ?? {}).map(([decision, count]: [string, number]) => (
            <span key={decision} className={`badge ${decisionBadgeClass(decision, true)} gap-1`}>
              <strong>{count}</strong> {decision}
            </span>
          ))}
        </div>
      </div>

      <div className="mb-4 rounded-lg border border-base-300 bg-base-100 p-4">
        <div className="grid gap-3 text-sm md:grid-cols-5">
          <div>
            <div className="text-xs uppercase text-base-content/50">Model</div>
            <div className="mt-1">{run.model || "-"}</div>
          </div>
          <div>
            <div className="text-xs uppercase text-base-content/50">Requested by</div>
            <div className="mt-1">{run.requested_by || "-"}</div>
          </div>
          <div>
            <div className="text-xs uppercase text-base-content/50">Entity type</div>
            <div className="mt-1">{run.entity_type}</div>
          </div>
          <div>
            <div className="text-xs uppercase text-base-content/50">Trigger</div>
            <div className="mt-1">{run.trigger_type}</div>
          </div>
          <div>
            <div className="text-xs uppercase text-base-content/50">Execution</div>
            <div className="mt-1">
              {run.execution_ids.length === 1
                ? run.execution_ids[0]
                : `${run.execution_ids.length} executions`}
            </div>
          </div>
          <div>
            <div className="text-xs uppercase text-base-content/50">Status</div>
            <div className="mt-1">
              {run.running_count + run.requested_count > 0
                ? `${run.running_count + run.requested_count} active`
                : "complete"}
            </div>
          </div>
        </div>
      </div>

      <div className="space-y-3">
        {data.items.map((item) => (
          <ReviewCard key={item.task_id} item={item} />
        ))}
      </div>
    </PageContainer>
  );
}
