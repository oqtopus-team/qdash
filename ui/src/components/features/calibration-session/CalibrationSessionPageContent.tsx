"use client";

import Link from "next/link";
import type { ReactNode } from "react";

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
import { ReportedOriginBadge } from "@/components/features/execution/ExecutionCalibrationContext";
import { getStatusBadgeClass } from "@/components/features/execution/ExecutionListCard";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { QubitTile } from "@/components/ui/QubitTile";
import { useAuth } from "@/contexts/AuthContext";
import {
  calibrationSessionsHref,
  dispatchStatusStyle,
  runDisplayName,
  runKindLabel,
  runTriggerLabel,
} from "@/lib/chatCalibrationSession";
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

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="text-xs text-base-content/60">{label}</div>
      <div className="mt-1 text-sm">{children}</div>
    </div>
  );
}

function executionHref(chipId: string, executionId: string, projectId: string | null) {
  const path = `/execution/${encodeURIComponent(chipId)}/${encodeURIComponent(executionId)}`;
  return projectId ? `${path}?project=${encodeURIComponent(projectId)}` : path;
}

function StatusBadge({ status }: { status: string }) {
  return (
    <span className={`badge badge-soft badge-sm ${getStatusBadgeClass(status)}`}>{status}</span>
  );
}

function ExecutionLinks({
  chipId,
  executions,
  projectId,
}: {
  chipId: string;
  executions: ExecutionResponseSummary[];
  projectId: string | null;
}) {
  if (executions.length === 0) return null;
  return (
    <ul className="flex flex-col gap-1">
      {executions.map((execution) => (
        <li key={execution.execution_id} className="flex items-center justify-between gap-2">
          <Link
            href={executionHref(chipId, execution.execution_id, projectId)}
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
  projectId,
}: {
  run: CalibrationPipelineRunResponse;
  projectId: string | null;
}) {
  const dispatch = dispatchStatusStyle(run.dispatch_status);
  const steps = run.pipeline?.steps ?? [];
  const executions = run.executions ?? [];
  const trigger = runTriggerLabel(run.trigger);
  return (
    <li className="flex flex-col gap-2 py-3" data-testid="calibration-pipeline-run">
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
                    href={executionHref(run.chip_id, step.execution_id, projectId)}
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
        <ExecutionLinks chipId={run.chip_id} executions={executions} projectId={projectId} />
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
}: {
  chipId: string;
  agent: CalibrationAgentSessionChild;
  projectId: string | null;
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
      <ExecutionLinks chipId={chipId} executions={executions} projectId={projectId} />
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
  const session = useGetCalibrationSession(calibrationSessionId, {
    query: {
      queryKey: [...getGetCalibrationSessionQueryKey(calibrationSessionId), projectId],
      enabled: projectId !== null,
      refetchInterval: (query) => (query.state.data?.data.status === "open" ? REFRESH_MS : false),
    },
    request: projectId ? projectRequest(projectId) : undefined,
  });
  const data = session.data?.data;

  if (linked.status === "unavailable" || linked.status === "no_project") {
    return (
      <PageContainer maxWidth>
        <PageHeader title="Calibration session" />
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
        <PageHeader title="Calibration session" />
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
  return (
    <PageContainer maxWidth>
      <PageHeader
        title="Calibration session"
        description={`${data.chip_id} · created by ${data.created_by} ${formatDateTime(data.created_at)}`}
        actions={
          <Link href={calibrationSessionsHref({ projectId })} className="btn btn-ghost btn-sm">
            All calibration sessions
          </Link>
        }
      />
      <div className="flex flex-col gap-4">
        <section className="card card-border bg-base-100">
          <div className="card-body grid gap-3 p-4 sm:grid-cols-2 md:grid-cols-4">
            <div className="sm:col-span-2 md:col-span-4">
              <Field label="Objective">
                <p className="whitespace-pre-wrap wrap-anywhere">{data.objective}</p>
              </Field>
            </div>
            <Field label="Status">
              <span
                className={`badge badge-soft badge-sm ${isOpen ? "badge-info" : "badge-ghost"}`}
              >
                {isOpen ? "Open" : "Closed"}
              </span>
            </Field>
            <Field label="Origin">
              {data.origin === "automatic" ? (
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
              {data.origin === "automatic"
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
          executionHref={(executionId) => executionHref(data.chip_id, executionId, projectId)}
        />

        <section className="card card-border bg-base-100" aria-label="Runs">
          <div className="card-body gap-1 p-4">
            <h2 className="text-sm font-medium">Runs</h2>
            <ListedOf shown={runs.length} total={runTotal} noun="runs" />
            {runs.length === 0 ? (
              <EmptyState
                title="No runs"
                description="Workflows, pipelines, and tasks started with this session's ID appear here, each with all of its step executions"
                emoji="empty"
              />
            ) : (
              <ul className="flex flex-col divide-y divide-base-content/10">
                {runs.map((run) => (
                  <PipelineRunItem key={run.run_id} run={run} projectId={projectId} />
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
