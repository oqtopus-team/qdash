"use client";

import Link from "next/link";

import { Target, Wrench } from "lucide-react";

import type {
  CalibrationSessionRef,
  ExecutionCalibrationSessionLink,
  ReportedLaunchOrigin,
} from "@/schemas";

import { calibrationSessionHref } from "@/lib/chatCalibrationSession";

/**
 * "Agent tool, reported": the caller said an agent tool launched the pipeline. QDash stores the
 * report as given and never verifies it, so the label always says reported and never reads as
 * the verified "Agent" of an agent session action.
 */
function reportedOriginLabel(origin: ReportedLaunchOrigin): string {
  return origin.source === "agent_tool" ? "Agent tool, reported" : `${origin.source}, reported`;
}

/** Who reported the origin and through which tool, for a tooltip or a sentence. */
function reportedOriginDetail(origin: ReportedLaunchOrigin): string {
  const by = origin.client ? `${origin.client} reported` : "The caller reported";
  return `${by} that the agent tool ${origin.tool} launched it; QDash does not verify this`;
}

export function ReportedOriginBadge({ origin }: { origin: ReportedLaunchOrigin }) {
  return (
    <span
      className="badge badge-ghost badge-sm shrink-0 gap-1"
      title={reportedOriginDetail(origin)}
      data-testid="reported-origin-badge"
    >
      <Wrench className="h-3 w-3" aria-hidden="true" />
      {reportedOriginLabel(origin)}
    </span>
  );
}

/**
 * The objective an execution belongs to, as plain text: list cards are buttons themselves, so
 * the badge holds no link; the details panel and page carry it.
 */
export function CalibrationSessionBadge({ link }: { link: CalibrationSessionRef }) {
  return (
    <span
      className="badge badge-outline badge-sm min-w-0 max-w-full gap-1"
      title={`Calibration session: ${link.objective}`}
      data-testid="calibration-session-badge"
    >
      <Target className="h-3 w-3 shrink-0" aria-hidden="true" />
      <span className="sr-only">Calibration session: </span>
      <span className="truncate">{link.objective || link.calibration_session_id}</span>
    </span>
  );
}

function membershipText(link: ExecutionCalibrationSessionLink): string {
  if (link.via === "pipeline_run") {
    return `A step of pipeline run ${link.pipeline_run_id ?? ""} recorded in this calibration session`;
  }
  return `Run by agent session ${link.agent_session_id ?? ""}, which was admitted to this calibration session`;
}

/**
 * Why an execution belongs to a calibration session, with a link back to its page in the
 * project the execution was read from, and the origin its launch reported, if any. Renders
 * nothing for an ordinary execution.
 */
export function ExecutionCalibrationNotice({
  link,
  origin,
  projectId,
  className = "",
}: {
  link?: ExecutionCalibrationSessionLink | null;
  origin?: ReportedLaunchOrigin | null;
  projectId?: string | null;
  className?: string;
}) {
  if (!link && !origin) return null;
  return (
    <div
      role="note"
      className={`alert alert-soft text-sm ${className}`}
      data-testid="execution-calibration-notice"
    >
      {link ? (
        <Target className="h-4 w-4" aria-hidden="true" />
      ) : (
        <Wrench className="h-4 w-4" aria-hidden="true" />
      )}
      <div className="flex min-w-0 flex-col gap-0.5">
        {link ? (
          <>
            <span className="wrap-anywhere">
              Calibration session: <span className="font-medium">{link.objective}</span> (
              {link.status === "open" ? "open" : "closed"})
            </span>
            <span className="text-base-content/70">{membershipText(link)}.</span>
          </>
        ) : null}
        {origin ? (
          <span className="text-base-content/70">
            {reportedOriginDetail(origin)}. The recorded user started it with their own sign-in.
          </span>
        ) : null}
      </div>
      {link ? (
        <Link
          href={calibrationSessionHref(link.calibration_session_id, projectId)}
          className="link link-hover whitespace-nowrap"
        >
          Open calibration session
        </Link>
      ) : null}
    </div>
  );
}
