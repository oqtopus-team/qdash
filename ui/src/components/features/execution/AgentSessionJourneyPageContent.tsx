"use client";

import Link from "next/link";
import { useState, type ReactNode } from "react";

import { ArrowLeft, ExternalLink } from "lucide-react";

import type { AgentJourneyNode, AgentSessionJourneyResponse } from "@/schemas";

import {
  getGetAgentSessionJourneyQueryKey,
  useGetAgentSessionJourney,
} from "@/client/execution/execution";
import {
  interventionReasonLabel,
  interventionStatusStyle,
  sessionStatusLabel,
} from "@/components/features/agent-session/interventionLabels";
import {
  projectRequest,
  useLinkedProject,
} from "@/components/features/agent-session/useLinkedProject";
import { TaskResultPreviewSidebar } from "@/components/features/task-results/TaskResultPreviewSidebar";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { QubitTile } from "@/components/ui/QubitTile";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import { formatDateTime } from "@/lib/utils/datetime";

import {
  measurementExecutionText,
  pluralize,
  sessionActivityLabel,
  sessionAuditHref,
  sessionJourneyHref,
  sessionStatusBadgeClass,
} from "./agentSessionDisplay";
import {
  AgentSessionJourneyGraph,
  EDGE_KIND_LABELS,
  KIND_LABELS,
} from "./AgentSessionJourneyGraph";
import { AgentActorLabel, recordedUserLabel } from "./ExecutionAttribution";
import { getStatusBadgeClass } from "./ExecutionListCard";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="text-xs text-base-content/60">{label}</div>
      <div className="mt-1 text-sm">{children}</div>
    </div>
  );
}

function nodeStatusBadge(node: AgentJourneyNode): { label: string; badge: string } {
  if (node.kind === "intervention") return interventionStatusStyle(node.status);
  if (node.kind === "measurement") {
    return { label: node.status.replace(/_/g, " "), badge: getStatusBadgeClass(node.status) };
  }
  return { label: node.status.replace(/_/g, " "), badge: "badge-ghost" };
}

function interventionHref(sessionId: string, interventionId: string, projectId: string) {
  return `/agent-sessions/${encodeURIComponent(sessionId)}/interventions/${encodeURIComponent(interventionId)}?project=${encodeURIComponent(projectId)}`;
}

function NodeLinks({
  node,
  chipId,
  sessionId,
  projectId,
}: {
  node: AgentJourneyNode;
  chipId: string;
  sessionId: string;
  projectId: string;
}) {
  const links: { href: string; label: string }[] = [];
  const measurement = node.measurement;
  if (measurement?.execution_id) {
    links.push({
      href: `/execution/${encodeURIComponent(chipId)}/${encodeURIComponent(measurement.execution_id)}`,
      label: "Execution",
    });
  }
  if (measurement?.task_id) {
    links.push({
      href: `/task-results/${encodeURIComponent(measurement.task_id)}`,
      label: "Result and figures",
    });
  }
  if (node.intervention) {
    links.push({
      href: interventionHref(sessionId, node.intervention.intervention_id, projectId),
      label: "Intervention",
    });
  }
  if (node.decision || node.proposal) {
    links.push({ href: sessionAuditHref(sessionId, projectId), label: "Audit" });
  }
  if (links.length === 0) return null;
  return (
    <span className="flex flex-wrap gap-x-3">
      {links.map((link) => (
        <Link key={link.href} href={link.href} className="link link-hover">
          {link.label}
        </Link>
      ))}
    </span>
  );
}

/** What the selected step says: a judgment's reading, an expert exchange, or a measurement. */
function SelectedNodeDetail({
  node,
  byId,
  chipId,
  sessionId,
  projectId,
  onSelect,
  onClose,
}: {
  node: AgentJourneyNode;
  byId: Map<string, AgentJourneyNode>;
  chipId: string;
  sessionId: string;
  projectId: string;
  onSelect: (nodeId: string) => void;
  onClose: () => void;
}) {
  const reference = (actionId: string) => {
    const target = byId.get(`action:${actionId}`);
    return target ? (
      <button
        key={actionId}
        type="button"
        className="link link-hover"
        onClick={() => onSelect(target.node_id)}
      >
        {target.order + 1}. {target.label}
      </button>
    ) : (
      <span key={actionId} className="font-mono text-xs text-base-content/60">
        {actionId} (not in this view)
      </span>
    );
  };
  const status = nodeStatusBadge(node);
  return (
    <section
      className="card card-border bg-base-100"
      aria-labelledby="journey-selected-heading"
      data-testid="journey-selected"
    >
      <div className="card-body gap-3 p-4">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h2 id="journey-selected-heading" className="text-sm font-medium">
            {node.order + 1}. {KIND_LABELS[node.kind] ?? node.kind}: {node.label}
          </h2>
          <div className="flex items-center gap-2">
            <span className={`badge badge-soft badge-sm ${status.badge}`}>{status.label}</span>
            <button type="button" className="btn btn-ghost btn-sm" onClick={onClose}>
              Close
            </button>
          </div>
        </div>
        <p className="text-xs text-base-content/60">{formatDateTime(node.at)}</p>
        {node.decision && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Assessment (agent reported)">
              {node.decision.assessment ?? "Not stated"}
            </Field>
            <Field label="Next action">
              {node.decision.next_action.replace(/_/g, " ")}
              {node.decision.next_detail ? `: ${node.decision.next_detail}` : ""}
              {node.decision.next_action_id && (
                <span className="block">{reference(node.decision.next_action_id)}</span>
              )}
            </Field>
            <div className="sm:col-span-2">
              <Field label="Rationale (agent reported)">{node.decision.interpretation}</Field>
            </div>
            <div className="sm:col-span-2">
              <Field label="Evidence">
                {(node.decision.evidence_action_ids ?? []).length === 0 &&
                (node.decision.evaluation_ids ?? []).length === 0 ? (
                  "No result cited"
                ) : (
                  <span className="flex flex-col items-start gap-1">
                    {(node.decision.evidence_action_ids ?? []).map(reference)}
                    {(node.decision.evaluation_ids ?? []).map((id) => (
                      <span key={id} className="font-mono text-xs text-base-content/60">
                        evaluation {id}
                      </span>
                    ))}
                  </span>
                )}
              </Field>
            </div>
            {node.decision.superseded_by_decision_id && (
              <p className="text-xs text-base-content/60 sm:col-span-2">
                Superseded by a later decision
              </p>
            )}
          </div>
        )}
        {node.intervention && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Reason">{interventionReasonLabel(node.intervention.reason)}</Field>
            <Field label="Answer">
              {node.intervention.response_decision
                ? `${node.intervention.response_decision} by ${node.intervention.responded_by ?? "unknown"}`
                : "Not answered yet"}
            </Field>
            <div className="sm:col-span-2">
              <Field label="Question (agent reported)">{node.intervention.question}</Field>
            </div>
            {node.intervention.response_guidance && (
              <div className="sm:col-span-2">
                <Field label="Guidance (expert statement)">
                  {node.intervention.response_guidance}
                </Field>
              </div>
            )}
          </div>
        )}
        {node.proposal && (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Why the policy rejected it">
              {node.proposal.reason || "Not recorded"}
            </Field>
            <Field label="Intent (agent reported)">{node.proposal.intent || "Not stated"}</Field>
            <p className="text-xs text-base-content/60 sm:col-span-2">
              A rejected proposal never reached hardware and has no execution
            </p>
          </div>
        )}
        {node.measurement && (
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Execution status">
              {measurementExecutionText(node.status, node.measurement)}
            </Field>
            <Field label="Task result">{node.measurement.task_status ?? "None yet"}</Field>
            <Field label="Evaluation">{node.measurement.evaluation_status ?? "None"}</Field>
          </div>
        )}
        {node.session_action && (
          <Field label="Action">{node.session_action.action_type.replace(/_/g, " ")}</Field>
        )}
        {(node.missing ?? []).length > 0 && (
          <p className="text-xs text-base-content/60">
            Not in the records: {(node.missing ?? []).join(", ")}
          </p>
        )}
        <NodeLinks node={node} chipId={chipId} sessionId={sessionId} projectId={projectId} />
      </div>
    </section>
  );
}

function JourneyBody({
  journey,
  chipId,
  sessionId,
  projectId,
}: {
  journey: AgentSessionJourneyResponse;
  chipId: string;
  sessionId: string;
  projectId: string;
}) {
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const { session, nodes, edges } = journey;
  const byId = new Map(nodes.map((node) => [node.node_id, node]));
  const selected = selectedNodeId ? byId.get(selectedNodeId) : undefined;
  const previewTaskId = selected?.measurement?.task_id ?? null;
  const { counts } = session;
  const outgoing = (nodeId: string) =>
    edges.filter((edge) => edge.source === nodeId && edge.kind !== "sequence");

  return (
    <div className="flex flex-col gap-4">
      <section className="card card-border bg-base-100" aria-label="Session">
        <div className="card-body grid gap-3 p-4 sm:grid-cols-2 md:grid-cols-4">
          <Field label="Session status">
            <span
              className={`badge badge-soft badge-sm ${sessionStatusBadgeClass(session.status)}`}
            >
              {sessionStatusLabel(session.status)}
            </span>
          </Field>
          <Field label="Activity">{sessionActivityLabel(session)}</Field>
          <Field label="Executions">
            {pluralize(counts.measurements, "execution")}
            {counts.pending_dispatch > 0 ? `, ${counts.pending_dispatch} not dispatched yet` : ""}
            {counts.dispatch_failed ? `, ${counts.dispatch_failed} failed to dispatch` : ""}
          </Field>
          <Field label="Actions used">
            {counts.actions} of {counts.max_actions}
          </Field>
          <Field label="Targets">
            <div className="flex flex-wrap gap-1">
              {session.qids.map((qid) => (
                <QubitTile key={qid} qid={qid} />
              ))}
            </div>
          </Field>
          <Field label="Decisions and experts">
            {pluralize(counts.decisions, "decision")},{" "}
            {pluralize(counts.open_interventions, "open question")}
          </Field>
          <Field label="Rejected proposals">{counts.rejected_proposals}</Field>
          <Field label="Expires">{formatDateTime(session.expires_at)}</Field>
          <div className="flex flex-wrap items-center gap-2 sm:col-span-2 md:col-span-4">
            <Link href={sessionAuditHref(sessionId, projectId)} className="btn btn-sm">
              <ExternalLink data-icon="inline-start" aria-hidden="true" />
              Policy and audit
            </Link>
            {session.status === "waiting_for_human" && session.active_intervention_id && (
              <Link
                href={interventionHref(sessionId, session.active_intervention_id, projectId)}
                className="btn btn-sm btn-warning"
              >
                Answer the expert request
              </Link>
            )}
          </div>
          <p className="text-xs text-base-content/60 sm:col-span-2 md:col-span-4">
            The session is the agent request: its policy, budget, and pauses. Each measurement is
            its own execution with its own status; the session holds no hardware between them.
            {(session.missing ?? []).length > 0
              ? ` Not in the records: ${(session.missing ?? []).join(", ")}.`
              : ""}
          </p>
        </div>
      </section>

      {!journey.complete && (
        <div role="status" className="alert alert-soft text-sm">
          <span>
            Showing the latest {nodes.length} of {journey.total_nodes} steps; the audit holds every
            record
          </span>
        </div>
      )}

      <section className="card card-border bg-base-100" aria-labelledby="journey-graph-heading">
        <div className="card-body gap-3 p-4">
          <h2 id="journey-graph-heading" className="text-sm font-medium">
            Journey
          </h2>
          {nodes.length === 0 ? (
            <p className="text-sm text-base-content/60">The agent has not proposed a step yet</p>
          ) : (
            <AgentSessionJourneyGraph
              nodes={nodes}
              edges={edges}
              selectedNodeId={selectedNodeId}
              onSelect={setSelectedNodeId}
            />
          )}
        </div>
      </section>

      {selected && !previewTaskId && (
        <SelectedNodeDetail
          node={selected}
          byId={byId}
          chipId={chipId}
          sessionId={sessionId}
          projectId={projectId}
          onSelect={setSelectedNodeId}
          onClose={() => setSelectedNodeId(null)}
        />
      )}

      <section className="card card-border bg-base-100" aria-labelledby="journey-steps-heading">
        <div className="card-body gap-3 p-4">
          <h2 id="journey-steps-heading" className="text-sm font-medium">
            Steps in time order
          </h2>
          <div className="overflow-x-auto">
            <table className="table table-sm">
              <thead>
                <tr>
                  <th>#</th>
                  <th>Time</th>
                  <th>Step</th>
                  <th>Status</th>
                  <th>Links to</th>
                  <th>Records</th>
                </tr>
              </thead>
              <tbody>
                {nodes.map((node) => {
                  const status = nodeStatusBadge(node);
                  const links = outgoing(node.node_id);
                  return (
                    <tr
                      key={node.node_id}
                      className={node.node_id === selectedNodeId ? "bg-primary/10" : undefined}
                    >
                      <td className="font-mono text-xs">{node.order + 1}</td>
                      <td className="text-xs text-base-content/60">{formatDateTime(node.at)}</td>
                      <td>
                        <button
                          type="button"
                          className="link link-hover text-left"
                          onClick={() => setSelectedNodeId(node.node_id)}
                        >
                          <span className="block text-xs text-base-content/60">
                            {KIND_LABELS[node.kind] ?? node.kind}
                          </span>
                          {node.label}
                        </button>
                      </td>
                      <td>
                        <span className={`badge badge-soft badge-sm ${status.badge}`}>
                          {status.label}
                        </span>
                      </td>
                      <td className="text-xs">
                        {links.length === 0
                          ? "—"
                          : links.map((edge) => {
                              const target = byId.get(edge.target);
                              return (
                                <span key={edge.edge_id} className="block">
                                  {EDGE_KIND_LABELS[edge.kind]}{" "}
                                  {target ? `${target.order + 1}` : "(not shown)"}
                                </span>
                              );
                            })}
                      </td>
                      <td className="text-xs">
                        <NodeLinks
                          node={node}
                          chipId={chipId}
                          sessionId={sessionId}
                          projectId={projectId}
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-base-content/60">
            Generated {formatDateTime(journey.generated_at)} from a live read of the records, not a
            snapshot. Agent decisions and questions are the agent&apos;s statements.
          </p>
        </div>
      </section>

      <TaskResultPreviewSidebar taskId={previewTaskId} onClose={() => setSelectedNodeId(null)} />
    </div>
  );
}

/**
 * One agent session as an experiment journey over its real executions, on the Execution page.
 * The session page stays the place for policy and the full audit.
 */
export function AgentSessionJourneyPageContent({
  chipId,
  sessionId,
}: {
  chipId: string;
  sessionId: string;
}) {
  const linked = useLinkedProject();
  const projectId = linked.status === "ready" ? linked.projectId : null;
  const journey = useGetAgentSessionJourney(sessionId, {
    query: {
      queryKey: [...getGetAgentSessionJourneyQueryKey(sessionId), projectId],
      enabled: projectId !== null,
      refetchInterval: 5000,
      refetchIntervalInBackground: true,
    },
    request: projectId ? projectRequest(projectId) : undefined,
  });
  const data = journey.data?.data;
  const backHref = `/execution?chip=${encodeURIComponent(chipId)}`;
  const back = (
    <Link href={backHref} className="btn btn-ghost btn-sm w-fit">
      <ArrowLeft data-icon="inline-start" aria-hidden="true" />
      Back to Executions
    </Link>
  );

  if (linked.status === "unavailable" || linked.status === "no_project") {
    return (
      <PageContainer>
        {back}
        <PageHeader title="Agent session" />
        <div role="alert" className="alert alert-error alert-soft">
          <span>
            {linked.status === "unavailable"
              ? `This agent session belongs to project ${linked.projectId}, which your account cannot open`
              : "Your account has no project, so this agent session cannot be opened"}
          </span>
        </div>
      </PageContainer>
    );
  }
  if (linked.status === "pending" || journey.isLoading) {
    return (
      <PageContainer>
        <div className="flex flex-col gap-4" aria-busy="true">
          <div className="skeleton h-8 w-60" />
          <div className="skeleton h-32 w-full" />
        </div>
      </PageContainer>
    );
  }
  if (journey.isError || !data || !projectId) {
    return (
      <PageContainer>
        {back}
        <PageHeader title="Agent session" />
        <div role="alert" className="alert alert-error alert-soft">
          <span>{getApiErrorMessage(journey.error, "This agent session could not be loaded")}</span>
        </div>
      </PageContainer>
    );
  }
  if (data.session.chip_id !== chipId) {
    return (
      <PageContainer>
        {back}
        <PageHeader title="Agent session" />
        <div role="alert" className="alert alert-warning alert-soft">
          <span>
            This agent session ran on chip {data.session.chip_id}, not {chipId}
          </span>
          <Link
            href={sessionJourneyHref(data.session.chip_id, sessionId, projectId)}
            className="link"
          >
            Open it on {data.session.chip_id}
          </Link>
        </div>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      {back}
      <PageHeader
        title={data.session.skill_name || "Agent session"}
        description={
          <span className="inline-flex flex-wrap items-center gap-x-2 gap-y-1">
            <span>{data.session.chip_id}</span>
            <span aria-hidden="true">·</span>
            <AgentActorLabel userLabel={recordedUserLabel(null, data.session.created_by)} />
            <span aria-hidden="true">·</span>
            <span>
              Started {formatDateTime(data.session.created_at)}
              {data.session.model_name ? ` · Model: ${data.session.model_name}` : ""}
            </span>
          </span>
        }
      />
      {/* A new project or session starts with nothing selected. */}
      <JourneyBody
        key={`${projectId}:${sessionId}`}
        journey={data}
        chipId={chipId}
        sessionId={sessionId}
        projectId={projectId}
      />
    </PageContainer>
  );
}
