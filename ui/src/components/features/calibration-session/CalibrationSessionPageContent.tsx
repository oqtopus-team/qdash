"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";

import { Info, Target } from "lucide-react";
import Link from "next/link";
import { useQueryStates } from "nuqs";

import {
  getGetCalibrationSessionQueryKey,
  useGetCalibrationSession,
} from "@/client/calibration-session/calibration-session";
import { sessionStatusLabel } from "@/components/features/agent-session/interventionLabels";
import {
  projectRequest,
  useLinkedProject,
} from "@/components/features/agent-session/useLinkedProject";
import {
  sessionAuditHref,
  sessionStatusBadgeClass,
} from "@/components/features/execution/agentSessionDisplay";
import { ExecutionBreadcrumbs } from "@/components/features/execution/ExecutionAreaNav";
import { ReportedOriginBadge } from "@/components/features/execution/ExecutionCalibrationContext";
import { getStatusBadgeClass } from "@/components/features/execution/ExecutionListCard";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { QubitTile } from "@/components/ui/QubitTile";
import { useAuth } from "@/contexts/AuthContext";
import {
  dispatchStatusStyle,
  runDisplayName,
  runKindLabel,
  runTriggerLabel,
} from "@/lib/chatCalibrationSession";
import {
  type ExecutionCrumb,
  type SessionReturnContext,
  calibrationSessionCrumbs,
  executionDetailHref,
  runAnchorId,
  runIdFromHash,
  sessionReturnFromQuery,
  sessionReturnParsers,
} from "@/lib/executionArea";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import { formatDateTime } from "@/lib/utils/datetime";
import type {
  CalibrationAgentSessionChild,
  CalibrationPipelineRunResponse,
  ExecutionResponseSummary,
} from "@/schemas";

import { CalibrationSearchProgress } from "./CalibrationSearchProgress";
import { CalibrationSessionAuditTimeline } from "./CalibrationSessionAuditTimeline";
import { CloseCalibrationSessionButton } from "./CloseCalibrationSessionButton";

/** How often an open session is read again while the page shows it. */
const REFRESH_MS = 15_000;

/** An objective longer than this, or on several lines, is also shown whole below the heading. */
const LONG_OBJECTIVE = 120;

/**
 * The list this page links back to, from its URL: the Executions list or the session list with
 * its filters. Only known parameters with valid values are read, and every link they build
 * stays on an Execution-area route.
 */
function useSessionReturn(): SessionReturnContext {
  const [state] = useQueryStates(sessionReturnParsers);
  return sessionReturnFromQuery(state);
}

/** The run the page's `#run-…` fragment names, read again when the fragment changes. */
function useTargetRunId(): string | null {
  const [runId, setRunId] = useState<string | null>(null);
  useEffect(() => {
    const read = () => setRunId(runIdFromHash(window.location.hash));
    read();
    window.addEventListener("hashchange", read);
    return () => window.removeEventListener("hashchange", read);
  }, []);
  return runId;
}

/** Builds the link to one execution of the session. */
type ExecutionLink = (chipId: string, executionId: string) => string;

/** The heading of a page that could not show its session. */
function PlainHeader({ crumbs }: { crumbs: ExecutionCrumb[] }) {
  return (
    <>
      <ExecutionBreadcrumbs crumbs={crumbs} />
      <PageHeader title="Calibration session" className="mt-2" />
    </>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="text-xs text-base-content/60">{label}</div>
      <div className="mt-1 text-sm">{children}</div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`badge badge-soft badge-sm ${getStatusBadgeClass(status)}`}>{status}</span>
  );
}

function ExecutionLinks({
  chipId,
  executions,
  executionLink,
}: {
  chipId: string;
  executions: ExecutionResponseSummary[];
  executionLink: ExecutionLink;
}) {
  if (executions.length === 0) return null;
  return (
    <ul className="flex flex-col gap-1">
      {executions.map((execution) => (
        <li key={execution.execution_id} className="flex items-center justify-between gap-2">
          <Link
            href={executionLink(chipId, execution.execution_id)}
            className="link link-hover truncate font-mono text-xs"
          >
            {execution.execution_id}
          </Link>
          <StatusBadge status={execution.status} />
        </li>
      ))}
    </ul>
  );
}

/** One run: its launch, then each planned step and the execution it ran in. */
function PipelineRunItem({
  run,
  executionLink,
  targeted,
}: {
  run: CalibrationPipelineRunResponse;
  executionLink: ExecutionLink;
  /** Whether the link that opened the page pointed at this run. */
  targeted: boolean;
}) {
  const dispatch = dispatchStatusStyle(run.dispatch_status);
  const steps = run.pipeline?.steps ?? [];
  const executions = run.executions ?? [];
  const trigger = runTriggerLabel(run.trigger);
  return (
    <li
      id={runAnchorId(run.run_id)}
      className={`flex scroll-mt-20 flex-col gap-2 py-3 ${
        targeted ? "-mx-2 rounded-box bg-base-200 px-2" : ""
      }`}
      aria-current={targeted ? "location" : undefined}
      data-testid="calibration-pipeline-run"
    >
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">{runDisplayName(run)}</span>
        <span className="badge badge-outline badge-sm">{runKindLabel(run.run_kind)}</span>
        {trigger ? <span className="badge badge-ghost badge-sm">{trigger}</span> : null}
        <span className={`badge badge-soft badge-sm ${dispatch.badge}`}>{dispatch.label}</span>
        {run.pipeline ? <StatusBadge status={run.pipeline.status} /> : null}
        {run.reported_origin ? <ReportedOriginBadge origin={run.reported_origin} /> : null}
        <span className="ml-auto text-xs text-base-content/60">
          {run.requested_by} · {formatDateTime(run.requested_at)}
        </span>
      </div>
      {run.dispatch_status === "unknown" ? (
        <p className="text-xs text-warning">
          QDash could not confirm whether this run started. It was admitted, so it may be running or
          may still start, even after the session is closed. Check the Execution list before
          starting it again.
        </p>
      ) : null}
      {run.dispatch_status === "rejected" && run.error ? (
        <p className="text-xs text-base-content/60">Not started: {run.error}</p>
      ) : null}
      {steps.length > 0 ? (
        <ol className="flex flex-col gap-1">
          {steps.map((step) => (
            <li key={step.index} className="flex items-center justify-between gap-2 text-xs">
              <span className="min-w-0 truncate">
                {step.index}. {step.name}
              </span>
              <span className="flex shrink-0 items-center gap-2">
                {step.execution_id ? (
                  <Link
                    href={executionLink(run.chip_id, step.execution_id)}
                    className="link link-hover font-mono"
                  >
                    {step.execution_id}
                  </Link>
                ) : null}
                <StatusBadge status={step.status} />
              </span>
            </li>
          ))}
        </ol>
      ) : (
        <ExecutionLinks
          chipId={run.chip_id}
          executions={executions}
          executionLink={executionLink}
        />
      )}
    </li>
  );
}

/** Says that a list shows only the most recent children, and how many there are in all. */
function ListedOf({ shown, total, noun }: { shown: number; total: number; noun: string }) {
  if (total <= shown) return null;
  return (
    <p className="text-xs text-base-content/60" data-testid="calibration-list-cut">
      Showing the latest {shown} of {total} {noun}. Close checks every one of them.
    </p>
  );
}

function AgentSessionItem({
  chipId,
  agent,
  projectId,
  executionLink,
}: {
  chipId: string;
  agent: CalibrationAgentSessionChild;
  projectId: string | null;
  executionLink: ExecutionLink;
}) {
  const executions = agent.executions ?? [];
  return (
    <li className="flex flex-col gap-2 py-3" data-testid="calibration-agent-session">
      <div className="flex flex-wrap items-center gap-2">
        <Link
          href={sessionAuditHref(agent.session_id, projectId)}
          className="link link-hover text-sm font-medium"
        >
          Agent session
        </Link>
        <span className={`badge badge-soft badge-sm ${sessionStatusBadgeClass(agent.status)}`}>
          {sessionStatusLabel(agent.status)}
        </span>
        {agent.calibration_admission === "pending" ? (
          <span className="badge badge-soft badge-sm badge-warning">Not admitted yet</span>
        ) : null}
        {agent.calibration_admission === "rejected" ? (
          <span className="badge badge-soft badge-sm">Rejected</span>
        ) : null}
        <span className="text-xs text-base-content/60">
          {agent.autonomy === "auto" ? "Autonomous calibration" : "Confirm each step"} ·{" "}
          {agent.action_count} action{agent.action_count === 1 ? "" : "s"}
        </span>
        <span className="ml-auto text-xs text-base-content/60">
          {agent.created_by} · {formatDateTime(agent.created_at)}
        </span>
      </div>
      <div className="flex flex-wrap gap-1">
        {agent.qids.map((qid) => (
          <QubitTile key={qid} qid={qid} />
        ))}
      </div>
      <ExecutionLinks chipId={chipId} executions={executions} executionLink={executionLink} />
    </li>
  );
}

export function CalibrationSessionPageContent({
  calibrationSessionId,
}: {
  calibrationSessionId: string;
}) {
  const linked = useLinkedProject();
  const { username } = useAuth();
  const projectId = linked.status === "ready" ? linked.projectId : null;
  const sessionReturn = useSessionReturn();
  const crumbs = calibrationSessionCrumbs(sessionReturn, projectId);
  const targetRunId = useTargetRunId();
  // Opened from the Executions list, an execution page returns to that list's view, as long as
  // the execution is on the chip that view shows.
  const executionLink: ExecutionLink = (chipId, executionId) =>
    executionDetailHref(
      chipId,
      executionId,
      projectId,
      sessionReturn.from === "executions" && sessionReturn.list.chip === chipId
        ? sessionReturn.list
        : undefined,
    );
  const session = useGetCalibrationSession(calibrationSessionId, {
    query: {
      queryKey: [...getGetCalibrationSessionQueryKey(calibrationSessionId), projectId],
      enabled: projectId !== null,
      refetchInterval: (query) => (query.state.data?.data.status === "open" ? REFRESH_MS : false),
    },
    request: projectId ? projectRequest(projectId) : undefined,
  });
  const data = session.data?.data;
  const targetRunShown =
    targetRunId !== null && (data?.pipeline_runs ?? []).some((run) => run.run_id === targetRunId);

  // The fragment's run appears only once the session has loaded, after the browser looked for
  // it; bring it into view then, once per fragment.
  const scrolledToRun = useRef<string | null>(null);
  useEffect(() => {
    if (!targetRunId || !targetRunShown || scrolledToRun.current === targetRunId) return;
    scrolledToRun.current = targetRunId;
    document.getElementById(runAnchorId(targetRunId))?.scrollIntoView({ block: "start" });
  }, [targetRunId, targetRunShown]);

  if (linked.status === "unavailable" || linked.status === "no_project") {
    return (
      <PageContainer maxWidth>
        <PlainHeader crumbs={crumbs} />
        <div role="alert" className="alert alert-error alert-soft">
          <span>
            {linked.status === "unavailable"
              ? `This calibration session belongs to project ${linked.projectId}, which your account cannot open. Ask a project owner for access.`
              : "Your account has no project, so this calibration session cannot be opened. Ask a project owner for access."}
          </span>
        </div>
      </PageContainer>
    );
  }
  if (linked.status === "pending" || session.isLoading) {
    return (
      <PageContainer maxWidth>
        <div className="flex flex-col gap-4" aria-busy="true">
          <div className="skeleton h-8 w-60" />
          <div className="skeleton h-32 w-full" />
        </div>
      </PageContainer>
    );
  }
  if (session.isError || !data) {
    return (
      <PageContainer maxWidth>
        <PlainHeader crumbs={crumbs} />
        <div role="alert" className="alert alert-error alert-soft">
          <span>
            {getApiErrorMessage(session.error, "This calibration session could not be loaded")}
          </span>
        </div>
      </PageContainer>
    );
  }

  const runs = data.pipeline_runs ?? [];
  const agents = data.agent_sessions ?? [];
  const runTotal = data.pipeline_run_total ?? runs.length;
  const agentTotal = data.agent_session_total ?? agents.length;
  const blockers = data.close_blockers ?? [];
  const unknownAgentStarts = (data.unknown_starts ?? []).map((start) => start.child_id);
  const isOpen = data.status === "open";
  const isAutomatic = data.origin === "automatic";
  const longObjective = data.objective.length > LONG_OBJECTIVE || data.objective.includes("\n");
  return (
    <PageContainer maxWidth>
      <header className="mb-4 flex min-w-0 flex-col gap-1 sm:mb-6">
        <ExecutionBreadcrumbs crumbs={crumbs} />
        <p className="mt-2 flex items-center gap-1.5 text-xs font-medium text-base-content/60">
          <Target className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {isAutomatic ? "Automatic calibration session" : "Calibration session"}
        </p>
        {/* The objective names the session; for an automatic one it is the run's recorded name. */}
        <h1 className="line-clamp-3 text-xl font-medium wrap-anywhere">{data.objective}</h1>
        <p className="text-sm text-base-content/70">
          {data.chip_id} · created by {data.created_by} {formatDateTime(data.created_at)}
        </p>
      </header>
      <div className="flex flex-col gap-4">
        <section className="card card-border bg-base-100" aria-label="Summary">
          <div className="card-body grid gap-3 p-4 sm:grid-cols-2 md:grid-cols-4">
            {longObjective ? (
              <div className="sm:col-span-2 md:col-span-4">
                <Field label="Objective">
                  <p className="whitespace-pre-wrap wrap-anywhere">{data.objective}</p>
                </Field>
              </div>
            ) : null}
            <Field label="Status">
              <span
                className={`badge badge-soft badge-sm ${isOpen ? "badge-info" : "badge-ghost"}`}
              >
                {isOpen ? "Open" : "Closed"}
              </span>
            </Field>
            <Field label="Origin">
              {isAutomatic ? (
                <span
                  className="badge badge-ghost badge-sm"
                  title="QDash created this session for a run started without one"
                >
                  Automatic
                </span>
              ) : (
                <span className="badge badge-ghost badge-sm">Created for an objective</span>
              )}
            </Field>
            <Field label="Runs">{runTotal}</Field>
            <Field label="Agent sessions">{agentTotal}</Field>
            <Field label="Still running or waiting">{blockers.length}</Field>
            <Field label="Decisions">{data.decision_total ?? 0}</Field>
            {!isOpen ? (
              <div className="sm:col-span-2 md:col-span-4">
                <Field label="Closed">
                  {data.closed_by} · {formatDateTime(data.closed_at ?? null)}
                  {data.closing_note ? `: ${data.closing_note}` : ""}
                </Field>
              </div>
            ) : null}
            <p className="text-xs text-base-content/60 sm:col-span-2 md:col-span-4">
              Groups the work started for this objective. It grants nothing: each run is approved on
              its own, and each agent session keeps its own policy and pause.
              {isAutomatic
                ? " QDash created it for a run started without a session; start another run with its ID to add to it."
                : ""}
            </p>
            {isOpen && projectId && username === data.created_by ? (
              <div className="sm:col-span-2 md:col-span-4">
                <CloseCalibrationSessionButton
                  calibrationSessionId={calibrationSessionId}
                  projectId={projectId}
                  blockers={blockers}
                  unknownRuns={data.unknown_runs ?? []}
                  unknownAgentStarts={unknownAgentStarts}
                  onClosed={() => void session.refetch()}
                />
              </div>
            ) : null}
          </div>
        </section>

        <CalibrationSearchProgress
          experiments={data.experiments ?? []}
          recommendation={data.recommendation}
          latestRun={data.latest_requested_run}
          executionHref={(executionId) => executionLink(data.chip_id, executionId)}
        />

        <section className="card card-border bg-base-100" aria-label="Runs">
          <div className="card-body gap-1 p-4">
            <h2 className="text-sm font-medium">Runs</h2>
            <ListedOf shown={runs.length} total={runTotal} noun="runs" />
            {targetRunId && !targetRunShown ? (
              <div
                role="status"
                className="alert alert-info alert-soft my-2 text-sm"
                data-testid="calibration-run-not-listed"
              >
                <Info className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span className="wrap-anywhere">
                  {runs.length > 0
                    ? `Run ${targetRunId} is not among the latest ${runs.length} runs listed here.`
                    : `Run ${targetRunId} is not listed here.`}{" "}
                  Its executions stay on the Execution list.
                </span>
              </div>
            ) : null}
            {runs.length === 0 ? (
              <EmptyState
                title="No runs"
                description="Workflows, pipelines, and tasks started with this session's ID appear here, each with all of its step executions"
                emoji="empty"
              />
            ) : (
              <ul className="flex flex-col divide-y divide-base-content/10">
                {runs.map((run) => (
                  <PipelineRunItem
                    key={run.run_id}
                    run={run}
                    executionLink={executionLink}
                    targeted={run.run_id === targetRunId}
                  />
                ))}
              </ul>
            )}
          </div>
        </section>

        <section className="card card-border bg-base-100" aria-label="Agent sessions">
          <div className="card-body gap-1 p-4">
            <h2 className="text-sm font-medium">Agent sessions</h2>
            <ListedOf shown={agents.length} total={agentTotal} noun="agent sessions" />
            {agents.length === 0 ? (
              <EmptyState
                title="No agent sessions"
                description="Agent sessions created with this session's ID appear here with the executions they ran"
                emoji="robot"
              />
            ) : (
              <ul className="flex flex-col divide-y divide-base-content/10">
                {agents.map((agent) => (
                  <AgentSessionItem
                    key={agent.session_id}
                    chipId={data.chip_id}
                    agent={agent}
                    projectId={projectId}
                    executionLink={executionLink}
                  />
                ))}
              </ul>
            )}
          </div>
        </section>
        {projectId ? (
          <CalibrationSessionAuditTimeline
            calibrationSessionId={calibrationSessionId}
            projectId={projectId}
          />
        ) : null}
      </div>
    </PageContainer>
  );
}
