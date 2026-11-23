"use client";

import Link from "next/link";

import {
  getGetCalibrationSessionQueryKey,
  useGetCalibrationSession,
} from "@/client/calibration-session/calibration-session";
import { projectRequest } from "@/components/features/agent-session/useLinkedProject";
import { useProject } from "@/contexts/ProjectContext";
import { calibrationSessionHref } from "@/lib/chatCalibrationSession";

/** How often an open calibration session is read again while the chat shows it. */
const REFRESH_MS = 30_000;
/** Calibration sessions one chat shows, the most recently named first. */
const MAX_SHOWN = 3;

function CalibrationSessionRow({ calibrationSessionId }: { calibrationSessionId: string }) {
  const { projectId } = useProject();
  const session = useGetCalibrationSession(calibrationSessionId, {
    query: {
      queryKey: [...getGetCalibrationSessionQueryKey(calibrationSessionId), projectId],
      enabled: projectId !== null,
      retry: false,
      refetchInterval: (query) => (query.state.data?.data.status === "open" ? REFRESH_MS : false),
    },
    request: projectId ? projectRequest(projectId) : undefined,
  });
  const data = session.data?.data;
  // Not found in this project, or not readable: say nothing rather than guess.
  if (!data || session.isError) return null;
  // Totals count every child, beyond the page the detail lists.
  const runs = data.pipeline_run_total ?? data.pipeline_runs?.length ?? 0;
  const agents = data.agent_session_total ?? data.agent_sessions?.length ?? 0;
  const active = data.close_blockers?.length ?? 0;
  const isOpen = data.status === "open";
  return (
    <li
      className="flex min-w-0 items-center gap-1.5"
      data-testid="chat-calibration-session"
      data-status={data.status}
    >
      <span
        className={`status status-xs shrink-0 ${active > 0 ? "status-info" : isOpen ? "status-neutral" : "status-success"}`}
        aria-hidden="true"
      />
      <span className="min-w-0 truncate font-medium text-base-content/80">{data.objective}</span>
      <span className="shrink-0 text-base-content/60">
        {isOpen ? "" : "Closed · "}
        {runs} pipeline run{runs === 1 ? "" : "s"} · {agents} agent session
        {agents === 1 ? "" : "s"}
        {active > 0 ? ` · ${active} running or waiting` : ""}
      </span>
      <Link
        href={calibrationSessionHref(calibrationSessionId, projectId)}
        className="link link-hover ml-auto shrink-0 text-base-content/60"
      >
        Open
      </Link>
    </li>
  );
}

/**
 * The calibration sessions this chat's tool calls named, each read from QDash under the
 * project open now: the objective, how many pipeline runs and agent sessions it groups, and
 * how many still run or wait. The chat is an entry point; QDash's records decide what belongs
 * to each session.
 */
export function ChatCalibrationSessions({
  calibrationSessionIds,
}: {
  calibrationSessionIds: string[];
}) {
  const shown = calibrationSessionIds.slice(-MAX_SHOWN).reverse();
  if (shown.length === 0) return null;
  return (
    <section
      className="rounded-[var(--radius-box)] border border-base-300 bg-base-100 px-3 py-2.5 text-xs"
      aria-label="Calibration sessions"
    >
      <ul className="flex flex-col gap-1.5">
        {shown.map((id) => (
          <CalibrationSessionRow key={id} calibrationSessionId={id} />
        ))}
      </ul>
    </section>
  );
}
