"use client";

import {
  exportAgentSessionAudit,
  getAgentSessionAudit,
  getGetAgentSessionAuditQueryKey,
} from "@/client/agent-session/agent-session";
import { AUDIT_PAGE_SIZE, AuditTimeline } from "@/components/features/audit/AuditTimeline";
import { reportedModelLabel } from "@/components/features/execution/agentSessionDisplay";
import type { AgentSessionAuditResponse } from "@/schemas";

import { projectRequest } from "./useLinkedProject";

/**
 * The agent session's chronological experiment audit (``AuditTimeline``), with the model the
 * creating host reported and the identity facts the session did not record.
 */
export function AgentSessionAuditTimeline({
  sessionId,
  projectId,
}: {
  sessionId: string;
  projectId: string;
}) {
  const request = projectRequest(projectId);
  return (
    <AuditTimeline<AgentSessionAuditResponse>
      title="Experiment audit"
      description="Steps, results, decisions, and expert answers, oldest first"
      source={{
        queryKey: [...getGetAgentSessionAuditQueryKey(sessionId), projectId],
        sessionId,
        filename: `agent-session-${sessionId}-audit.json`,
        fetchPage: async (cursor, signal) =>
          (
            await getAgentSessionAudit(
              sessionId,
              { limit: AUDIT_PAGE_SIZE, ...(cursor ? { cursor } : {}) },
              request,
              signal,
            )
          ).data,
        exportAll: async () => (await exportAgentSessionAudit(sessionId, request)).data,
      }}
      header={(first) => {
        const sessionModel = first?.session.model;
        const missingIdentity = first?.session.missing ?? [];
        if (!sessionModel && missingIdentity.length === 0) return null;
        return (
          <p className="text-xs text-base-content/60">
            {sessionModel ? (
              <span>
                Created with model {reportedModelLabel(sessionModel)}, reported by{" "}
                {sessionModel.host || "the client"} and not verified by QDash.
              </span>
            ) : null}
            {sessionModel && missingIdentity.length ? " " : null}
            {missingIdentity.length ? (
              <span>The session did not record: {missingIdentity.join(", ")}.</span>
            ) : null}
          </p>
        );
      }}
    />
  );
}
