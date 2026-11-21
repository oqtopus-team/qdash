"use client";

import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { Download, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import {
  exportAgentSessionAudit,
  getAgentSessionAudit,
  getGetAgentSessionAuditQueryKey,
} from "@/client/agent-session/agent-session";
import type { AgentAuditEvent, AgentSessionAuditResponse } from "@/schemas";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import { formatDateTime } from "@/lib/utils/datetime";

import { projectRequest } from "./useLinkedProject";

const AUDIT_PAGE_SIZE = 50;

const KIND_LABELS: Record<string, string> = {
  session_created: "Session approved",
  action_proposed: "Action proposed",
  measurement: "Measurement",
  evaluation: "Evaluation",
  decision: "Agent decision",
  candidate_commit: "Candidate commit",
  candidate_set_commit: "Candidate set commit",
  backend_apply: "Backend apply",
  intervention_opened: "Expert asked",
  intervention_response: "Expert answered",
  intervention_resumed: "Resumed",
  resume_outcome: "Resume outcome",
};

const PROVENANCE_LABELS: Record<string, string> = {
  server_record: "QDash record",
  server_computed: "Computed by QDash",
  agent_reported: "Agent statement",
  human_reported: "Expert statement",
  evaluator_reported: "Evaluator output",
};

export function auditKindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind;
}

export function auditProvenanceLabel(provenance: string): string {
  return PROVENANCE_LABELS[provenance] ?? provenance;
}

type Data = Record<string, unknown>;

function scalarList(value: unknown): string[] {
  if (!value || typeof value !== "object") return [];
  return Object.entries(value as Data).flatMap(([name, entry]) => {
    const raw = entry && typeof entry === "object" ? (entry as Data).value : entry;
    if (raw === null || raw === undefined || typeof raw === "object") return [];
    const unit = entry && typeof entry === "object" ? (entry as Data).unit : undefined;
    return [`${name} ${String(raw)}${unit ? ` ${String(unit)}` : ""}`];
  });
}

function EventLinks({ event, sessionId }: { event: AgentAuditEvent; sessionId: string }) {
  const links: { href: string; label: string }[] = [];
  if (event.execution_id && event.kind === "measurement") {
    links.push({
      href: `/executions/${encodeURIComponent(event.execution_id)}`,
      label: "Execution",
    });
  }
  if (event.task_id && event.kind === "measurement") {
    links.push({
      href: `/task-results/${encodeURIComponent(event.task_id)}`,
      label: "Result and figures",
    });
  }
  if (event.intervention_id && event.kind === "intervention_opened") {
    links.push({
      href: `/agent-sessions/${encodeURIComponent(sessionId)}/interventions/${encodeURIComponent(event.intervention_id)}`,
      label: "Intervention",
    });
  }
  if (links.length === 0) return null;
  return (
    <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
      {links.map((link) => (
        <Link key={link.href} href={link.href} className="link link-hover">
          {link.label}
        </Link>
      ))}
    </div>
  );
}

function EventDetail({ event }: { event: AgentAuditEvent }) {
  const data = (event.data ?? {}) as Data;
  const rows: { label: string; value: string }[] = [];
  if (event.kind === "action_proposed" && data.intent) {
    rows.push({ label: "Intent (agent)", value: String(data.intent) });
  }
  if (event.kind === "measurement") {
    const requested = scalarList(data.requested_overrides);
    if (requested.length) rows.push({ label: "Requested", value: requested.join(", ") });
    const outputs = scalarList(data.outputs);
    if (outputs.length) rows.push({ label: "Outputs", value: outputs.join(", ") });
    const metrics = scalarList(data.quality_metrics);
    if (metrics.length) rows.push({ label: "Quality metrics", value: metrics.join(", ") });
    const gate = Array.isArray(data.gate) ? (data.gate as Data[]) : [];
    if (gate.length) {
      rows.push({
        label: "Gate",
        value: gate
          .map((row) => `${String(row.parameter_name)} ${row.accepted ? "accepted" : "rejected"}`)
          .join(", "),
      });
    }
  }
  if (event.kind === "decision") {
    rows.push({ label: "Interpretation (agent)", value: String(data.interpretation ?? "") });
    if (data.superseded_by_decision_id) {
      rows.push({ label: "Superseded by", value: String(data.superseded_by_decision_id) });
    }
  }
  if (event.kind === "intervention_opened" && data.question) {
    rows.push({ label: "Question", value: String(data.question) });
  }
  if (event.kind === "intervention_response" && data.guidance) {
    rows.push({ label: "Guidance (expert)", value: String(data.guidance) });
  }
  if (rows.length === 0) return null;
  return (
    <dl className="mt-1 grid gap-x-3 gap-y-0.5 text-xs sm:grid-cols-[max-content_1fr]">
      {rows.map((row) => (
        <div key={row.label} className="contents">
          <dt className="text-base-content/60">{row.label}</dt>
          <dd className="break-words">{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function AuditEventItem({
  event,
  sessionId,
  first,
  last,
}: {
  event: AgentAuditEvent;
  sessionId: string;
  first: boolean;
  last: boolean;
}) {
  const missing = event.missing ?? [];
  return (
    <li>
      {first ? null : <hr />}
      <div className="timeline-middle">
        <span
          className={`block size-2.5 rounded-full ${
            event.provenance === "agent_reported"
              ? "bg-info"
              : event.provenance === "human_reported"
                ? "bg-accent"
                : "bg-base-content/40"
          }`}
          aria-hidden="true"
        />
      </div>
      <div className="timeline-end mb-4 min-w-0">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-base-content/60">
          <time dateTime={event.at}>{formatDateTime(event.at)}</time>
          <span className="font-medium text-base-content">{auditKindLabel(event.kind)}</span>
          <span className="badge badge-ghost badge-xs">
            {auditProvenanceLabel(event.provenance)}
          </span>
          {event.actor ? <span>{event.actor}</span> : null}
          {event.status_is_current && event.status ? (
            <span title="Live status of a record that can still change">now {event.status}</span>
          ) : null}
        </div>
        <p className="mt-0.5 text-sm break-words">{event.summary}</p>
        <EventDetail event={event} />
        {missing.length ? (
          <p className="mt-1 text-xs text-warning">Not recorded: {missing.join(", ")}</p>
        ) : null}
        <EventLinks event={event} sessionId={sessionId} />
      </div>
      {last ? null : <hr />}
    </li>
  );
}

function downloadJson(audit: AgentSessionAuditResponse, sessionId: string) {
  const blob = new Blob([JSON.stringify(audit, null, 2)], {
    type: "application/json;charset=utf-8",
  });
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `agent-session-${sessionId}-audit.json`;
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  window.URL.revokeObjectURL(url);
}

function statusOf(error: unknown): number | undefined {
  const status = (error as { response?: { status?: unknown } } | null)?.response?.status;
  return typeof status === "number" ? status : undefined;
}

/**
 * The session's chronological experiment audit, read from QDash a page at a time, with a
 * JSON export of the whole timeline. Every entry says whose statement it is.
 *
 * Each read is one snapshot of QDash's records. The pages shown always come from the
 * snapshot of the first page: when the records change before the next page is read, QDash
 * refuses it (409) and the timeline offers to read the audit again from the start instead
 * of joining pages of two snapshots.
 */
export function AgentSessionAuditTimeline({
  sessionId,
  projectId,
}: {
  sessionId: string;
  projectId: string;
}) {
  const request = projectRequest(projectId);
  const queryClient = useQueryClient();
  const queryKey = [...getGetAgentSessionAuditQueryKey(sessionId), projectId, "pages"];
  const audit = useInfiniteQuery({
    queryKey,
    queryFn: async ({ pageParam, signal }) =>
      (
        await getAgentSessionAudit(
          sessionId,
          { limit: AUDIT_PAGE_SIZE, ...(pageParam ? { cursor: pageParam } : {}) },
          request,
          signal,
        )
      ).data,
    initialPageParam: null as string | null,
    getNextPageParam: (page) => (page.complete ? undefined : (page.next_cursor ?? undefined)),
  });
  const [exporting, setExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exportNewer, setExportNewer] = useState(false);

  const allPages = audit.data?.pages ?? [];
  const snapshotId = allPages[0]?.snapshot_id;
  // Only pages of the first page's snapshot are shown; another snapshot's page is never joined.
  const pages = allPages.filter((page) => page.snapshot_id === snapshotId);
  const changed =
    pages.length < allPages.length || (audit.isError && statusOf(audit.error) === 409);
  const events = pages.flatMap((page) => page.events);
  const total = pages[0]?.total_events ?? 0;
  const missingIdentity = pages[0]?.session.missing ?? [];
  const readAt = pages[0]?.generated_at;

  const reload = () => {
    setExportNewer(false);
    void queryClient.resetQueries({ queryKey, exact: true });
  };

  const onExport = async () => {
    setExporting(true);
    setExportError(null);
    setExportNewer(false);
    try {
      const response = await exportAgentSessionAudit(sessionId, request);
      downloadJson(response.data, sessionId);
      setExportNewer(Boolean(snapshotId) && response.data.snapshot_id !== snapshotId);
    } catch (error) {
      setExportError(getApiErrorMessage(error, "The audit could not be exported"));
    } finally {
      setExporting(false);
    }
  };

  return (
    <section className="card card-border bg-base-100" aria-labelledby="audit-heading">
      <div className="card-body gap-3 p-4">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 id="audit-heading" className="text-sm font-medium">
              Experiment audit
            </h2>
            <p className="text-xs text-base-content/60">
              Every step, result, decision, commit, and expert answer, oldest first, from QDash
              records. Agent and expert statements are labeled as theirs.
            </p>
          </div>
          <div className="flex gap-2">
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={reload}
              disabled={audit.isFetching}
            >
              <RefreshCw data-icon="inline-start" aria-hidden="true" />
              Refresh
            </button>
            <button
              type="button"
              className="btn btn-sm"
              onClick={onExport}
              disabled={exporting || (audit.isError && events.length === 0)}
            >
              {exporting ? (
                <span className="loading loading-spinner loading-xs" data-icon="inline-start" />
              ) : (
                <Download data-icon="inline-start" aria-hidden="true" />
              )}
              Export JSON
            </button>
          </div>
        </div>
        {exportError ? (
          <div role="alert" className="alert alert-error alert-soft">
            <span>{exportError}</span>
          </div>
        ) : null}
        {exportNewer ? (
          <div role="status" className="alert alert-info alert-soft">
            <span>
              The exported file is a newer read of the audit than the timeline shown here: the
              records changed after the timeline loaded. Refresh to show the same records.
            </span>
          </div>
        ) : null}
        {missingIdentity.length ? (
          <p className="text-xs text-base-content/60">
            The session did not record: {missingIdentity.join(", ")}.
          </p>
        ) : null}
        {audit.isLoading ? (
          <div className="flex flex-col gap-2" aria-busy="true">
            <div className="skeleton h-6 w-full" />
            <div className="skeleton h-6 w-5/6" />
            <div className="skeleton h-6 w-4/6" />
          </div>
        ) : audit.isError && events.length === 0 ? (
          <div role="alert" className="alert alert-error alert-soft">
            <span>{getApiErrorMessage(audit.error, "The audit could not be loaded")}</span>
          </div>
        ) : (
          <>
            <ul className="timeline timeline-vertical timeline-compact timeline-snap-icon">
              {events.map((event, index) => (
                <AuditEventItem
                  key={event.event_id}
                  event={event}
                  sessionId={sessionId}
                  first={index === 0}
                  last={index === events.length - 1}
                />
              ))}
            </ul>
            <div className="flex flex-wrap items-center gap-3 text-xs text-base-content/60">
              <span>
                Showing {events.length} of {total} events
                {readAt ? ` as read at ${formatDateTime(readAt)}` : ""}
              </span>
              {changed ? null : audit.hasNextPage ? (
                <button
                  type="button"
                  className="btn btn-ghost btn-xs"
                  onClick={() => void audit.fetchNextPage()}
                  disabled={audit.isFetchingNextPage}
                >
                  {audit.isFetchingNextPage ? "Loading" : "Load more"}
                </button>
              ) : (
                <span>End of the timeline</span>
              )}
            </div>
            {changed ? (
              <div role="alert" className="alert alert-warning alert-soft">
                <span>
                  The audit changed while it was being read (a new result, decision, or status). The
                  events above are from the earlier read and stop here; read the audit again to see
                  all of it.
                </span>
                <button type="button" className="btn btn-sm" onClick={reload}>
                  Read again from the start
                </button>
              </div>
            ) : audit.isError ? (
              <div role="alert" className="alert alert-error alert-soft">
                <span>{getApiErrorMessage(audit.error, "More events could not be loaded")}</span>
              </div>
            ) : null}
          </>
        )}
      </div>
    </section>
  );
}
