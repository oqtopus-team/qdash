"use client";

import Link from "next/link";
import type { ReactNode } from "react";

import {
  getGetAgentSessionQueryKey,
  getListAgentInterventionsQueryKey,
  useGetAgentSession,
  useListAgentInterventions,
} from "@/client/agent-session/agent-session";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { calibrationSessionHref } from "@/lib/chatCalibrationSession";
import { QubitTile } from "@/components/ui/QubitTile";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import { formatDateTime } from "@/lib/utils/datetime";

import {
  interventionHref,
  interventionReasonLabel,
  interventionStatusStyle,
  sessionStatusLabel,
} from "./interventionLabels";
import {
  sessionGraphHref,
  sessionStatusBadgeClass,
} from "@/components/features/execution/agentSessionDisplay";

import { AgentSessionAuditTimeline } from "./AgentSessionAuditTimeline";
import { StopAgentSessionButton } from "./StopAgentSessionButton";
import { projectRequest, useLinkedProject } from "./useLinkedProject";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="text-xs text-base-content/60">{label}</div>
      <div className="mt-1 text-sm">{children}</div>
    </div>
  );
}

export function AgentSessionPageContent({ sessionId }: { sessionId: string }) {
  const linked = useLinkedProject();
  const projectId = linked.status === "ready" ? linked.projectId : null;
  const request = projectId ? projectRequest(projectId) : undefined;
  const session = useGetAgentSession(sessionId, {
    query: {
      queryKey: [...getGetAgentSessionQueryKey(sessionId), projectId],
      enabled: projectId !== null,
    },
    request,
  });
  const interventions = useListAgentInterventions(sessionId, {
    query: {
      queryKey: [...getListAgentInterventionsQueryKey(sessionId), projectId],
      enabled: projectId !== null,
    },
    request,
  });
  const data = session.data?.data;

  if (linked.status === "unavailable") {
    return (
      <PageContainer maxWidth>
        <PageHeader title="Agent session" />
        <div role="alert" className="alert alert-error alert-soft">
          <span>
            This agent session belongs to project {linked.projectId}, which your account cannot
            open. Ask a project owner for access.
          </span>
        </div>
      </PageContainer>
    );
  }
  if (linked.status === "no_project") {
    return (
      <PageContainer maxWidth>
        <PageHeader title="Agent session" />
        <div role="alert" className="alert alert-error alert-soft">
          <span>
            Your account has no project, so this agent session cannot be opened. Ask a project owner
            for access.
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
        <PageHeader title="Agent session" />
        <div role="alert" className="alert alert-error alert-soft">
          <span>{getApiErrorMessage(session.error, "This agent session could not be loaded")}</span>
        </div>
      </PageContainer>
    );
  }

  const items = interventions.data?.data.items ?? [];
  return (
    <PageContainer maxWidth>
      <PageHeader
        title="Agent session"
        description={`${data.chip_id} · created by ${data.created_by} ${formatDateTime(data.created_at)}`}
      />
      <div className="flex flex-col gap-4">
        <section className="card card-border bg-base-100">
          <div className="card-body grid gap-3 p-4 sm:grid-cols-2 md:grid-cols-4">
            <Field label="Status">
              <span className={`badge badge-soft badge-sm ${sessionStatusBadgeClass(data.status)}`}>
                {sessionStatusLabel(data.status)}
              </span>
            </Field>
            <Field label="Actions used">
              {data.action_count} of {data.policy.max_actions}
            </Field>
            <Field label="Expires">{formatDateTime(data.expires_at)}</Field>
            <Field label="Autonomy">
              {data.policy.autonomy === "auto" ? "Approved plan" : "Confirm each step"}
            </Field>
            <Field label="Targets">
              <div className="flex flex-wrap gap-1">
                {data.policy.qids.map((qid) => (
                  <QubitTile key={qid} qid={qid} />
                ))}
              </div>
            </Field>
            <div className="sm:col-span-2 md:col-span-3">
              <Field label="Allowed tasks">{data.policy.allowed_tasks.join(", ")}</Field>
            </div>
            {data.calibration_session_id ? (
              <div className="sm:col-span-2 md:col-span-4">
                <Field label="Calibration session">
                  <Link
                    href={calibrationSessionHref(data.calibration_session_id, projectId)}
                    className="link link-hover font-mono text-xs"
                  >
                    {data.calibration_session_id}
                  </Link>
                  {data.calibration_admission === "pending" ? (
                    <span className="ml-2 badge badge-soft badge-sm badge-warning">
                      Not admitted yet
                    </span>
                  ) : null}
                  {data.calibration_admission === "rejected" ? (
                    <span className="ml-2 badge badge-soft badge-sm">Rejected</span>
                  ) : null}
                </Field>
              </div>
            ) : null}
            {data.stop ? (
              <div className="sm:col-span-2 md:col-span-4">
                <Field label="Stopped">
                  {data.stop.stopped_by} · {formatDateTime(data.stop.stopped_at)}:{" "}
                  {data.stop.reason}
                </Field>
              </div>
            ) : null}
            <div className="flex flex-wrap items-center gap-3 sm:col-span-2 md:col-span-4">
              <Link
                href={sessionGraphHref(data.chip_id, sessionId, projectId)}
                className="link link-hover text-sm"
              >
                View the measurements on the Execution page
              </Link>
              {projectId && (data.status === "active" || data.status === "waiting_for_human") ? (
                <StopAgentSessionButton
                  sessionId={sessionId}
                  projectId={projectId}
                  onStopped={() => {
                    void session.refetch();
                    void interventions.refetch();
                  }}
                />
              ) : null}
            </div>
          </div>
        </section>

        <section className="card card-border bg-base-100">
          <div className="card-body gap-3 p-4">
            <h2 className="text-sm font-medium">Interventions</h2>
            {interventions.isError ? (
              <div role="alert" className="alert alert-error alert-soft">
                <span>
                  {getApiErrorMessage(interventions.error, "Interventions could not be loaded")}
                </span>
              </div>
            ) : items.length === 0 ? (
              <EmptyState
                title="No interventions"
                description="The agent has not stopped for an expert in this session"
                emoji="check"
              />
            ) : (
              <ul className="flex flex-col divide-y divide-base-content/10">
                {items.map((item) => {
                  const status = interventionStatusStyle(item.status);
                  return (
                    <li
                      key={item.intervention_id}
                      className="flex flex-col gap-1 py-2 sm:flex-row sm:items-center sm:justify-between"
                    >
                      <div className="min-w-0">
                        <Link href={interventionHref(item)} className="link link-hover">
                          {interventionReasonLabel(item.reason)}
                          {item.task_name ? ` · ${item.task_name}` : ""}
                        </Link>
                        <p className="truncate text-xs text-base-content/60">{item.question}</p>
                      </div>
                      <div className="flex shrink-0 items-center gap-2">
                        <span className="text-xs text-base-content/60">
                          {formatDateTime(item.created_at)}
                        </span>
                        <span className={`badge badge-soft badge-sm ${status.badge}`}>
                          {status.label}
                        </span>
                      </div>
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        </section>

        {projectId ? (
          <AgentSessionAuditTimeline sessionId={sessionId} projectId={projectId} />
        ) : null}
      </div>
    </PageContainer>
  );
}
