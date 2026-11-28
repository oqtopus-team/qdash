"use client";

import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { Download, RefreshCw } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import type { ReactNode } from "react";

import type { AgentAuditEvent } from "@/schemas";
import {
  reportedModelLabel,
  reportedModelTitle,
} from "@/components/features/execution/agentSessionDisplay";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import { formatDateTime } from "@/lib/utils/datetime";
import { saveBlob } from "@/lib/utils/download";

export const AUDIT_PAGE_SIZE = 50;

/** One page of an audit snapshot: an agent session's or a calibration session's. */
export interface AuditPageLike {
  snapshot_id: string;
  events: AgentAuditEvent[];
  total_events: number;
  complete: boolean;
  next_cursor?: string | null;
  generated_at: string;
}

/** Gate outcome of one candidate; an out-of-scope output is not a failed check. */
export function gateOutcomeLabel(row: { accepted?: unknown; rejection?: unknown }): string {
  if (row.accepted) return "accepted";
  if (row.rejection === "not_in_scope") return "not in session scope (reference only)";
  if (row.rejection === "outside_bounds") return "rejected: outside bounds";
  if (row.rejection === "quality_gate") return "rejected: quality gate";
  return "rejected";
}

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
  session_stopped: "Session stopped",
  pipeline_requested: "Pipeline requested",
  pipeline_dispatch: "Dispatch",
  agent_session_linked: "Agent session",
  session_closed: "Session closed",
};

const PROVENANCE_LABELS: Record<string, string> = {
  server_record: "QDash record",
  server_computed: "Computed by QDash",
  agent_reported: "Agent statement",
  human_reported: "Expert statement",
  evaluator_reported: "Evaluator output",
  client_reported: "Client statement",
};

/** Whose audit a timeline shows; a calibration session's own creation is not an approval. */
export type AuditScope = "agent_session" | "calibration_session";

/** A decision without a reported model may be a person's: it is not called an agent's. */
export function auditKindLabel(
  kind: string,
  provenance?: string,
  scope: AuditScope = "agent_session",
  agentSessionId?: string | null,
): string {
  if (kind === "decision" && provenance === "client_reported") return "Decision";
  if (kind === "session_created" && scope === "calibration_session" && !agentSessionId) {
    return "Session opened";
  }
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
  // An agent session's event inside a calibration session's audit links to that agent session.
  sessionId = event.agent_session_id ?? sessionId;
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

/** The event's payload as label/value rows, for its details disclosure. */
function eventDetailRows(event: AgentAuditEvent): { label: string; value: string }[] {
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
    const gate = gateRows(event);
    if (gate.length) {
      rows.push({
        label: "Gate",
        value: gate
          .map((row) => `${String(row.parameter_name)} ${gateOutcomeLabel(row)}`)
          .join(", "),
      });
    }
  }
  if (event.kind === "measurement" && Array.isArray(data.tasks)) {
    for (const task of data.tasks as Data[]) {
      const executed = scalarList(task.executed_run_parameters);
      const outputs = scalarList(task.outputs);
      rows.push({
        label: `${String(task.name)} ${String(task.qid ?? "")} (${String(task.status)})`,
        value: [
          executed.length ? `executed ${executed.join(", ")}` : "",
          outputs.length ? `outputs ${outputs.join(", ")}` : "",
        ]
          .filter(Boolean)
          .join("; "),
      });
    }
  }
  if (event.kind === "pipeline_requested" && Array.isArray(data.requested_task_calls)) {
    const requested = (data.requested_task_calls as Data[]).flatMap((call) => {
      const run = scalarList(call.run);
      return run.length ? [`${String(call.call_id ?? call.task_name)}: ${run.join(", ")}`] : [];
    });
    if (requested.length) rows.push({ label: "Requested", value: requested.join("; ") });
  }
  if (event.kind === "decision") {
    const who = event.provenance === "agent_reported" ? "agent" : "client";
    rows.push({ label: `Interpretation (${who})`, value: String(data.interpretation ?? "") });
    const experiment = data.experiment as Data | null | undefined;
    if (experiment) {
      const changes = Array.isArray(experiment.requested_changes)
        ? (experiment.requested_changes as Data[])
            .map(
              (change) =>
                `${String(change.task_name)}.${String(change.parameter)} = ${String(change.value)}`,
            )
            .join(", ")
        : "";
      rows.push({
        label: "Experiment",
        value: `${String(experiment.stage)} ${String(experiment.candidate_id)} on ${String(experiment.target)}${changes ? `: ${changes}` : ""}`,
      });
    }
    const conclusion = data.conclusion as Data | null | undefined;
    if (conclusion) {
      rows.push({
        label: "Conclusion",
        value: `${String(conclusion.outcome)}${conclusion.recommended_candidate_id ? ` ${String(conclusion.recommended_candidate_id)}` : ""}`,
      });
    }
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
  return rows;
}

function gateRows(event: AgentAuditEvent): Data[] {
  const gate = (event.data as Data | undefined)?.gate;
  return Array.isArray(gate) ? (gate as Data[]) : [];
}

/** Gate checks that failed; an out-of-scope output is reference only, not a failure. */
function failedGateCount(event: AgentAuditEvent): number {
  if (event.kind !== "measurement") return 0;
  return gateRows(event).filter((row) => !row.accepted && row.rejection !== "not_in_scope").length;
}

/**
 * The event's secondary facts — who recorded it, the model its record reported, and its
 * payload — behind a per-event disclosure, so the timeline reads as kind, source, and summary.
 */
function EventDetails({ event, label }: { event: AgentAuditEvent; label: string }) {
  const rows = eventDetailRows(event);
  const meta: { label: string; value: ReactNode }[] = [];
  if (event.actor) meta.push({ label: "Recorded by", value: event.actor });
  if (event.model) {
    meta.push({
      label: "Model",
      value: <span title={reportedModelTitle(event.model)}>{reportedModelLabel(event.model)}</span>,
    });
  }
  const all = [...meta, ...rows];
  if (all.length === 0) return null;
  return (
    <details className="mt-1 text-xs" data-testid="audit-event-details">
      <summary className="w-fit cursor-pointer text-base-content/60 hover:text-base-content">
        Details<span className="sr-only">: {label}</span>
      </summary>
      <dl className="mt-1 grid gap-x-3 gap-y-0.5 sm:grid-cols-[max-content_1fr]">
        {all.map((row) => (
          <div key={row.label} className="contents">
            <dt className="text-base-content/60">{row.label}</dt>
            <dd className="break-words">{row.value}</dd>
          </div>
        ))}
      </dl>
    </details>
  );
}

function AuditEventItem({
  event,
  sessionId,
  scope,
  first,
  last,
}: {
  event: AgentAuditEvent;
  sessionId: string;
  scope: AuditScope;
  first: boolean;
  last: boolean;
}) {
  const missing = event.missing ?? [];
  const kindLabel = auditKindLabel(event.kind, event.provenance, scope, event.agent_session_id);
  const failedGates = failedGateCount(event);
  const superseded =
    event.kind === "decision" && Boolean((event.data as Data)?.superseded_by_decision_id);
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
          <span className="font-medium text-base-content">{kindLabel}</span>
          {event.agent_session_id ? (
            <span className="badge badge-soft badge-info badge-xs">
              Agent session {event.agent_session_id.slice(0, 8)}
            </span>
          ) : null}
          <span className="badge badge-ghost badge-xs">
            {auditProvenanceLabel(event.provenance)}
          </span>
          {event.status_is_current && event.status ? (
            <span title="Live status of a record that can still change">now {event.status}</span>
          ) : null}
          {failedGates ? (
            <span className="badge badge-soft badge-warning badge-xs">
              {failedGates} gate check{failedGates === 1 ? "" : "s"} failed
            </span>
          ) : null}
          {superseded ? <span className="badge badge-ghost badge-xs">Superseded</span> : null}
        </div>
        <p className="mt-0.5 text-sm break-words">{event.summary}</p>
        {missing.length ? (
          <p className="mt-1 text-xs text-warning">Not recorded: {missing.join(", ")}</p>
        ) : null}
        <EventLinks event={event} sessionId={sessionId} />
        <EventDetails event={event} label={`${kindLabel}, ${formatDateTime(event.at)}`} />
      </div>
      {last ? null : <hr />}
    </li>
  );
}

function downloadJson(audit: AuditPageLike, filename: string) {
  const blob = new Blob([JSON.stringify(audit, null, 2)], {
    type: "application/json;charset=utf-8",
  });
  saveBlob(blob, filename);
}

function statusOf(error: unknown): number | undefined {
  const status = (error as { response?: { status?: unknown } } | null)?.response?.status;
  return typeof status === "number" ? status : undefined;
}

/** Where an audit timeline reads its pages and its export. */
export interface AuditTimelineSource<P extends AuditPageLike> {
  queryKey: readonly unknown[];
  fetchPage: (cursor: string | null, signal: AbortSignal) => Promise<P>;
  exportAll: () => Promise<P>;
  filename: string;
  /** The session whose interventions the events link to, when an event names no other. */
  sessionId: string;
}

/**
 * A chronological audit, read from QDash a page at a time, with a JSON export of the whole
 * timeline. Every entry says whose statement it is. Agent sessions and calibration sessions
 * share it: both audits use the same event schema and snapshot rules. Each session feature
 * keeps a thin wrapper (`AgentSessionAuditTimeline`, `CalibrationSessionAuditTimeline`) that
 * supplies its own API calls, query key, export file name, and header.
 *
 * Each read is one snapshot of QDash's records. The pages shown always come from the
 * snapshot of the first page: when the records change before the next page is read, QDash
 * refuses it (409) and the timeline offers to read the audit again from the start instead
 * of joining pages of two snapshots.
 */
export function AuditTimeline<P extends AuditPageLike>({
  source,
  scope = "agent_session",
  title,
  description,
  header,
}: {
  source: AuditTimelineSource<P>;
  scope?: AuditScope;
  title: string;
  description?: string;
  header?: (first: P | undefined) => ReactNode;
}) {
  const queryClient = useQueryClient();
  const queryKey = [...source.queryKey, "pages"];
  const audit = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam, signal }) => source.fetchPage(pageParam, signal),
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
  const readAt = pages[0]?.generated_at;
  const sessionId = source.sessionId;

  const reload = () => {
    setExportNewer(false);
    void queryClient.resetQueries({ queryKey, exact: true });
  };

  const onExport = async () => {
    setExporting(true);
    setExportError(null);
    setExportNewer(false);
    try {
      const exported = await source.exportAll();
      downloadJson(exported, source.filename);
      setExportNewer(Boolean(snapshotId) && exported.snapshot_id !== snapshotId);
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
              {title}
            </h2>
            {description ? <p className="text-xs text-base-content/60">{description}</p> : null}
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
              The exported file is a newer read of the audit than this timeline. Refresh to match
              it.
            </span>
          </div>
        ) : null}
        {header ? header(pages[0]) : null}
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
                  scope={scope}
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
                  The audit changed while it was being read. The events above stop at the earlier
                  read.
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
