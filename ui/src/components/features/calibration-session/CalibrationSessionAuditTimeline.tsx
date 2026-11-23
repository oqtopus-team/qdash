"use client";

import {
  exportCalibrationSessionAudit,
  getCalibrationSessionAudit,
  getGetCalibrationSessionAuditQueryKey,
} from "@/client/calibration-session/calibration-session";
import { AUDIT_PAGE_SIZE, AuditTimeline } from "@/components/features/audit/AuditTimeline";
import { projectRequest } from "@/components/features/agent-session/useLinkedProject";
import type { CalibrationSessionAuditResponse } from "@/schemas";

/**
 * The calibration session's audit with the same timeline as an agent session's: decisions,
 * pipeline requests, dispatch outcomes, executions, and the events of its admitted agent
 * sessions, each labeled with whose record or statement it is.
 */
export function CalibrationSessionAuditTimeline({
  calibrationSessionId,
  projectId,
}: {
  calibrationSessionId: string;
  projectId: string;
}) {
  const request = projectRequest(projectId);
  return (
    <AuditTimeline<CalibrationSessionAuditResponse>
      scope="calibration_session"
      title="Audit"
      description="Every decision, pipeline request, dispatch outcome, execution, and agent session step, oldest first, from QDash records. Statements are labeled as such, and facts QDash never received are listed as not recorded."
      source={{
        queryKey: [...getGetCalibrationSessionAuditQueryKey(calibrationSessionId), projectId],
        sessionId: calibrationSessionId,
        filename: `calibration-session-${calibrationSessionId}-audit.json`,
        fetchPage: async (cursor, signal) =>
          (
            await getCalibrationSessionAudit(
              calibrationSessionId,
              { limit: AUDIT_PAGE_SIZE, ...(cursor ? { cursor } : {}) },
              request,
              signal,
            )
          ).data,
        exportAll: async () =>
          (await exportCalibrationSessionAudit(calibrationSessionId, request)).data,
      }}
    />
  );
}
