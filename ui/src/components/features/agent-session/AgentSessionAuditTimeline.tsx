"use client";

import {
  exportAgentSessionAudit,
  getAgentSessionAudit,
  getGetAgentSessionAuditQueryKey,
} from "@/client/agent-session/agent-session";
import { reportedModelLabel } from "@/components/features/execution/agentSessionDisplay";
import type { AgentSessionAuditResponse } from "@/schemas";

import { AUDIT_PAGE_SIZE, AuditTimeline } from "./AuditTimeline";
import { projectRequest } from "./useLinkedProject";

export { auditKindLabel, auditProvenanceLabel, gateOutcomeLabel } from "./AuditTimeline";

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
      description="Every step, result, decision, commit, and expert answer, oldest first, from QDash records. Agent and expert statements are labeled as theirs."
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
        return (
          <>
            {sessionModel ? (
              <p className="text-xs text-base-content/60">
                Created with model {reportedModelLabel(sessionModel)}, reported by{" "}
                {sessionModel.host || "the client"} and not verified by QDash. Each entry names the
                model its own record reported.
              </p>
            ) : null}
            {missingIdentity.length ? (
              <p className="text-xs text-base-content/60">
                The session did not record: {missingIdentity.join(", ")}.
              </p>
            ) : null}
          </>
        );
      }}
    />
  );
}
