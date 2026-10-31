"use client";

import {
  ArrowLeft,
  ArrowLeftRight,
  ChevronDown,
  ChevronRight,
  Image as ImageIcon,
  ThumbsDown,
  ThumbsUp,
  XCircle,
} from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { parseAsString, useQueryState } from "nuqs";
import { Fragment, useMemo, useState } from "react";

import { useGetEvaluationRun } from "@/client/evaluation/evaluation";
import { TaskFigure } from "@/components/charts/TaskFigure";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageContainer } from "@/components/ui/PageContainer";
import { PierreDiffViewer } from "@/components/ui/PierreDiffViewer";
import { formatDateTime } from "@/lib/utils/datetime";
import type { EvaluationItem, EvaluationRunSummary } from "@/schemas";

import { EvaluationCard } from "./EvaluationCard";
import {
  type CompareRow,
  type RunSide,
  joinEvaluations,
  runSettings,
  summarizeRows,
} from "./evaluationCompare";
import {
  agreementRate,
  diagnosisOf,
  diagnosisSuccess,
  fitAssessment,
  fitBadgeClass,
  fitLabel,
  runIsActive,
  statusLabel,
  runTimingLabel,
} from "./evaluationDisplay";
import { RunPicker } from "./RunPicker";

const SIDE_LABEL = { a: "A", b: "B" } as const;
type Side = keyof typeof SIDE_LABEL;

function useRun(runId: string | null) {
  return useGetEvaluationRun(runId ?? "", {
    query: {
      enabled: !!runId,
      refetchInterval: (query) => {
        const run = query.state.data?.data.run;
        return run && runIsActive(run) ? 5_000 : false;
      },
    },
  });
}

function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div title={hint}>
      <div className="text-xs uppercase text-base-content/50">{label}</div>
      <div className="mt-1 text-sm">{value}</div>
    </div>
  );
}

/** Headline of one run in the compare page. */
function RunHeadline({ side, run }: { side: Side; run: EvaluationRunSummary }) {
  const agreement = agreementRate(run);
  return (
    <div className="min-w-0 rounded-lg border border-base-300 bg-base-100 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="badge badge-primary badge-sm font-medium">{SIDE_LABEL[side]}</span>
        <Link
          href={`/evaluations/${run.run_id}`}
          className="link link-hover truncate font-mono text-xs"
        >
          {run.run_id}
        </Link>
        {runIsActive(run) && <span className="badge badge-info badge-sm">running</span>}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-base-content/60">
        <span>requested {formatDateTime(run.requested_at)}</span>
        <span>by {run.requested_by}</span>
        <span>
          {run.completed_count}/{run.total} done
        </span>
        {run.failed_count > 0 && <span className="text-error">{run.failed_count} failed</span>}
        {(run.interrupted_count ?? 0) > 0 && (
          <span className="text-warning">{run.interrupted_count} interrupted</span>
        )}
        {(run.cancelled_count ?? 0) > 0 && <span>{run.cancelled_count} cancelled</span>}
        {runTimingLabel(run) && <span>{runTimingLabel(run)}</span>}
      </div>
      <div className="mt-2 flex flex-wrap gap-2">
        <span className="badge badge-success badge-sm gap-1" title="Diagnoses reporting success">
          <strong>{run.success_count}</strong> success
        </span>
        <span className="badge badge-ghost badge-sm gap-1" title="Diagnoses with all six keys">
          <strong>{run.complete_count}</strong> complete
        </span>
        <span className="badge badge-outline badge-sm gap-1" title="People agreeing with the model">
          {agreement === null
            ? "not judged"
            : `${Math.round(agreement * 100)}% agreed · ${run.agree_count + run.disagree_count} judged`}
        </span>
      </div>
    </div>
  );
}

/** Side-by-side table of the recorded settings of two evaluation runs. */
function SettingsTable({ a, b }: { a: RunSide; b: RunSide }) {
  const settings = runSettings(a, b);
  const differing = settings.filter((setting) => setting.differs).length;
  return (
    <div className="rounded-lg border border-base-300 bg-base-100">
      <div className="flex items-center justify-between border-b border-base-300 px-4 py-2">
        <span className="text-sm font-medium">Settings</span>
        <span className="text-xs text-base-content/60">
          {differing === 0 ? "identical" : `${differing} differ`}
        </span>
      </div>
      <table className="table table-xs">
        <thead>
          <tr>
            <th className="w-40" />
            <th>A</th>
            <th>B</th>
          </tr>
        </thead>
        <tbody>
          {settings.map((setting) => (
            <tr
              key={setting.key}
              className={setting.differs ? "bg-warning/10" : ""}
              data-testid={`setting-${setting.key}`}
            >
              <td className="text-base-content/60">{setting.label}</td>
              <td className={`break-all ${setting.differs ? "font-medium" : ""}`}>{setting.a}</td>
              <td className={`break-all ${setting.differs ? "font-medium" : ""}`}>{setting.b}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function VerdictMark({ item }: { item: EvaluationItem }) {
  const agree = item.verdict?.agree ?? null;
  if (agree === true) return <ThumbsUp className="h-3.5 w-3.5 text-success" aria-label="agreed" />;
  if (agree === false)
    return <ThumbsDown className="h-3.5 w-3.5 text-error" aria-label="disagreed" />;
  return <span className="text-base-content/30">–</span>;
}

function JudgementCells({ item }: { item: EvaluationItem | null }) {
  if (!item) {
    return (
      <td colSpan={3} className="text-base-content/40">
        not in this run
      </td>
    );
  }
  if (item.status !== "completed") {
    return (
      <td colSpan={3}>
        <span
          className={`badge badge-sm ${item.status === "failed" ? "badge-error" : "badge-ghost"}`}
        >
          {item.status}
        </span>
      </td>
    );
  }
  const diagnosis = diagnosisOf(item);
  const fit = fitAssessment(diagnosis);
  const success = diagnosisSuccess(diagnosis);
  const status = statusLabel(diagnosis);
  return (
    <>
      <td>
        {fit ? (
          <span className={`badge badge-sm ${fitBadgeClass(fit)}`}>{fitLabel(fit)}</span>
        ) : (
          <span className="badge badge-sm badge-outline">
            {diagnosis ? (item.output?.complete === false ? "incomplete" : "-") : "prose"}
          </span>
        )}
      </td>
      <td>
        {status === null ? (
          <span className="text-base-content/40">-</span>
        ) : (
          <span className={`badge badge-sm ${success ? "badge-success" : "badge-warning"}`}>
            {status}
          </span>
        )}
      </td>
      <td>
        <VerdictMark item={item} />
      </td>
    </>
  );
}

function OutcomeBadge({ outcome, difference }: Pick<CompareRow, "outcome" | "difference">) {
  if (outcome === "same") return <span className="badge badge-sm badge-ghost">same</span>;
  if (outcome === "differs")
    return (
      <span className="badge badge-sm badge-warning">
        {difference === "decision" ? "decision differs" : "content differs"}
      </span>
    );
  return <span className="text-xs text-base-content/40">n/a</span>;
}

function DiagnosisDiff({ row }: { row: CompareRow }) {
  const [open, setOpen] = useState(false);
  const diagnosisA = row.a ? diagnosisOf(row.a) : null;
  const diagnosisB = row.b ? diagnosisOf(row.b) : null;
  if (!diagnosisA || !diagnosisB) return null;
  return (
    <details
      className="text-sm"
      onToggle={(event) => setOpen((event.target as HTMLDetailsElement).open)}
    >
      <summary className="cursor-pointer font-medium text-primary">
        Diagnosis A vs B
        <span className="ml-2 text-xs font-normal text-base-content/60">
          {row.outcome === "same"
            ? "identical"
            : row.difference === "decision"
              ? "decision differs"
              : "supporting content differs"}
        </span>
      </summary>
      {open && (
        <div className="mt-2">
          <PierreDiffViewer
            filename="diagnosis.json"
            oldContent={`${JSON.stringify(diagnosisA, null, 2)}\n`}
            newContent={`${JSON.stringify(diagnosisB, null, 2)}\n`}
            layout="split"
          />
        </div>
      )}
    </details>
  );
}

/**
 * The two prompts of one entity as a diff, A as the old side and B as the new,
 * so what changed between the runs (an edited reference, examples, a question,
 * what Copilot wrote as context) stands out. The diff is built only when opened.
 */
function PromptDiff({ row }: { row: CompareRow }) {
  const [open, setOpen] = useState(false);
  const promptA = row.a?.input?.prompt ?? null;
  const promptB = row.b?.input?.prompt ?? null;
  if (promptA === null || promptB === null) return null;
  const systemA = row.a?.input?.system_prompt ?? "";
  const systemB = row.b?.input?.system_prompt ?? "";
  const same = promptA === promptB && systemA === systemB;
  return (
    <details
      className="text-sm"
      onToggle={(event) => setOpen((event.target as HTMLDetailsElement).open)}
      data-testid="prompt-diff"
    >
      <summary className="cursor-pointer font-medium text-primary">
        Prompt A vs B
        <span className="ml-2 text-xs font-normal text-base-content/60">
          {same ? "identical" : "differs"}
        </span>
      </summary>
      {open && (
        <div className="mt-2 space-y-3">
          {systemA !== systemB && (
            <div>
              <div className="mb-1 text-xs uppercase text-base-content/50">System prompt</div>
              <PierreDiffViewer
                filename="system-prompt.txt"
                oldContent={systemA}
                newContent={systemB}
                layout="split"
              />
            </div>
          )}
          <div>
            <div className="mb-1 text-xs uppercase text-base-content/50">User turn</div>
            {same ? (
              <pre className="max-h-80 overflow-auto whitespace-pre-wrap rounded bg-base-100 p-2 text-xs">
                {promptA}
              </pre>
            ) : (
              <PierreDiffViewer
                filename="prompt.txt"
                oldContent={promptA}
                newContent={promptB}
                layout="split"
              />
            )}
          </div>
        </div>
      )}
    </details>
  );
}

/** The expanded detail of one compared entity. */
function ExpandedRow({ row }: { row: CompareRow }) {
  const shown = row.a ?? row.b;
  const figurePath = shown?.figure_path?.[0];
  const jsonFigurePath = shown?.json_figure_path?.[0];
  return (
    <tr className="bg-base-200/30">
      <td colSpan={9} className="space-y-4 p-3">
        <DiagnosisDiff row={row} />
        <PromptDiff row={row} />
        <div className="grid gap-4 xl:grid-cols-[minmax(0,360px)_minmax(0,1fr)]">
          <div className="rounded-lg border border-base-300 bg-base-200/40 p-3">
            {figurePath && shown ? (
              <div className="flex h-[280px] min-w-0 items-center justify-center overflow-hidden rounded-lg bg-white p-2">
                <TaskFigure path={figurePath} jsonFigurePath={jsonFigurePath} qid={shown.qid} fit />
              </div>
            ) : (
              <div className="flex h-[280px] flex-col items-center justify-center gap-2 text-sm text-base-content/50">
                <ImageIcon className="h-8 w-8" />
                No figure
              </div>
            )}
            {row.sameResult === false && (
              <p className="mt-2 text-xs text-warning">
                The two runs judged different results of this entity; the figure shown is A&apos;s.
              </p>
            )}
          </div>
          <div className="grid gap-3 lg:grid-cols-2">
            {(["a", "b"] as const).map((side) => {
              const item = row[side];
              return (
                <div key={side} className="min-w-0">
                  <div className="mb-1 text-xs font-medium text-base-content/60">
                    {SIDE_LABEL[side]}
                  </div>
                  {item ? (
                    <EvaluationCard item={item} showFigure={false} showTarget={false} />
                  ) : (
                    <div className="rounded-lg border border-dashed border-base-300 p-4 text-sm text-base-content/50">
                      Not evaluated in this run.
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      </td>
    </tr>
  );
}

function MissingSide({
  known,
  knownSide,
  onPick,
}: {
  known: EvaluationRunSummary;
  knownSide: Side;
  onPick: (runId: string) => void;
}) {
  const other = knownSide === "a" ? "B" : "A";
  return (
    <div className="space-y-4">
      <RunHeadline side={knownSide} run={known} />
      <div className="rounded-lg border border-base-300 bg-base-100 p-4">
        <div className="mb-2 text-sm font-medium">Choose run {other}</div>
        <p className="mb-3 text-xs text-base-content/60">
          Another run of {known.task_name} on {known.chip_id}.
        </p>
        <RunPicker
          chipId={known.chip_id}
          taskName={known.task_name}
          excludeRunId={known.run_id}
          onPick={onPick}
          label={`Pick run ${other}…`}
          className="w-full max-w-xl"
        />
      </div>
    </div>
  );
}

/** Two evaluation runs side by side: settings, totals, and every entity's two judgements. */
export function EvaluationComparePageContent() {
  const router = useRouter();
  const [runA, setRunA] = useQueryState("a", parseAsString);
  const [runB, setRunB] = useQueryState("b", parseAsString);
  const queryA = useRun(runA);
  const queryB = useRun(runB);
  const [onlyDifferences, setOnlyDifferences] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(() => new Set());

  const dataA = queryA.data?.data;
  const dataB = queryB.data?.data;
  const rows = useMemo(
    () => (dataA && dataB ? joinEvaluations(dataA.evaluations, dataB.evaluations) : []),
    [dataA, dataB],
  );
  const summary = useMemo(() => summarizeRows(rows), [rows]);
  const visibleRows = onlyDifferences
    ? rows.filter((row) => row.outcome === "differs" || row.outcome === "incomplete")
    : rows;

  const toggle = (qid: string) =>
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(qid)) next.delete(qid);
      else next.add(qid);
      return next;
    });
  const swap = () => {
    void setRunA(runB);
    void setRunB(runA);
  };

  const header = (
    <div className="mb-6 flex items-start justify-between gap-4">
      <div className="flex min-w-0 items-start gap-3">
        <button
          className="btn btn-square btn-ghost btn-sm shrink-0"
          onClick={() => router.push("/evaluations")}
          aria-label="Back to evaluation runs"
        >
          <ArrowLeft className="h-4 w-4" />
        </button>
        <div className="min-w-0">
          <h1 className="truncate text-xl font-medium">
            Compare runs
            {dataA && ` · ${dataA.run.task_name} · ${dataA.run.chip_id}`}
          </h1>
          <p className="mt-1 text-xs text-base-content/50">
            The same results judged twice, entity by entity. Comparison includes the complete
            structured diagnosis and distinguishes decision changes from supporting-content changes.
          </p>
        </div>
      </div>
      {runA && runB && (
        <button type="button" className="btn btn-ghost btn-sm gap-1" onClick={swap}>
          <ArrowLeftRight className="h-4 w-4" />
          Swap
        </button>
      )}
    </div>
  );

  if (!runA && !runB) {
    return (
      <PageContainer maxWidth>
        {header}
        <EmptyState
          title="Choose two runs"
          description="Select two runs on the AI Evaluations page, or open a run and pick another to compare with."
          emoji="robot"
          action={
            <Link href="/evaluations" className="btn btn-primary btn-sm">
              AI Evaluations
            </Link>
          }
        />
      </PageContainer>
    );
  }

  if ((runA && queryA.isLoading) || (runB && queryB.isLoading)) {
    return (
      <PageContainer maxWidth>
        {header}
        <div className="flex justify-center py-16">
          <span className="loading loading-spinner loading-lg" />
        </div>
      </PageContainer>
    );
  }

  if ((runA && (queryA.isError || !dataA)) || (runB && (queryB.isError || !dataB))) {
    return (
      <PageContainer maxWidth>
        {header}
        <div className="alert alert-error">
          <XCircle className="h-5 w-5" />
          <span>Failed to load one of the evaluation runs.</span>
        </div>
      </PageContainer>
    );
  }

  if (!dataA || !dataB) {
    const known = dataA ?? dataB;
    if (!known) return null;
    return (
      <PageContainer maxWidth>
        {header}
        <MissingSide
          known={known.run}
          knownSide={dataA ? "a" : "b"}
          onPick={(runId) => void (dataA ? setRunB(runId) : setRunA(runId))}
        />
      </PageContainer>
    );
  }

  return (
    <PageContainer maxWidth>
      {header}

      <div className="mb-4 grid gap-3 md:grid-cols-2">
        <RunHeadline side="a" run={dataA.run} />
        <RunHeadline side="b" run={dataB.run} />
      </div>

      <div className="mb-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <SettingsTable a={dataA} b={dataB} />
        <div className="rounded-lg border border-base-300 bg-base-100 p-4">
          <div className="mb-3 text-sm font-medium">Outcome</div>
          <div className="grid gap-3 sm:grid-cols-3">
            <Stat label="Entities" value={summary.rows} hint="Entities in either run" />
            <Stat
              label="In both runs"
              value={`${summary.paired} (${summary.sameResult} same result)`}
              hint="Entities evaluated on both sides, and how many of them judged the same task result"
            />
            <Stat
              label="Compared"
              value={summary.compared}
              hint="Rows where both sides answered in JSON"
            />
            <Stat label="Same outcome" value={summary.same} />
            <Stat label="Different outcome" value={summary.differs} />
            <Stat
              label="Success"
              value={`A ${dataA.run.success_count} · B ${dataB.run.success_count}`}
            />
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-base-300 bg-base-100">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-base-300 px-4 py-2">
          <span className="text-sm font-medium">
            {visibleRows.length} of {rows.length} entities
          </span>
          <label className="label cursor-pointer gap-2 py-0">
            <input
              type="checkbox"
              className="checkbox checkbox-sm"
              checked={onlyDifferences}
              onChange={(event) => setOnlyDifferences(event.target.checked)}
            />
            <span className="label-text text-xs">Only differences</span>
          </label>
        </div>
        {visibleRows.length === 0 ? (
          <div className="p-6 text-center text-sm text-base-content/50">
            {rows.length === 0 ? "No evaluations yet." : "No differences between the runs."}
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="table table-sm" data-testid="compare-table">
              <thead>
                <tr>
                  <th className="w-8" />
                  <th>Entity</th>
                  <th colSpan={3} className="border-l border-base-300">
                    A · fit / status / verdict
                  </th>
                  <th colSpan={3} className="border-l border-base-300">
                    B · fit / status / verdict
                  </th>
                  <th className="border-l border-base-300">Outcome</th>
                </tr>
              </thead>
              <tbody>
                {visibleRows.map((row) => {
                  const open = expanded.has(row.qid);
                  return (
                    <Fragment key={row.qid}>
                      <tr
                        className="cursor-pointer hover:bg-base-200/40"
                        onClick={() => toggle(row.qid)}
                        data-testid={`compare-row-${row.qid}`}
                      >
                        <td>
                          {open ? (
                            <ChevronDown className="h-4 w-4 text-base-content/50" />
                          ) : (
                            <ChevronRight className="h-4 w-4 text-base-content/50" />
                          )}
                        </td>
                        <td className="font-medium">
                          {row.qid}
                          {row.sameResult === false && (
                            <span
                              className="badge badge-warning badge-outline badge-xs ml-2"
                              title="The two runs judged different task results of this entity"
                            >
                              different results
                            </span>
                          )}
                        </td>
                        <JudgementCells item={row.a} />
                        <JudgementCells item={row.b} />
                        <td className="border-l border-base-300">
                          <OutcomeBadge outcome={row.outcome} difference={row.difference} />
                        </td>
                      </tr>
                      {open && <ExpandedRow row={row} />}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </PageContainer>
  );
}
