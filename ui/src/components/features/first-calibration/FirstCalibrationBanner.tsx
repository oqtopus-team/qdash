"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { CircleAlert, CircleCheck, GraduationCap } from "lucide-react";

import { HardwareReadinessCheck } from "./HardwareReadinessCheck";
import {
  JOURNEY_STEPS,
  executionHref,
  journeyNextAction,
  journeyShowsHardwareReadiness,
  journeyStageHint,
  journeyStepNumber,
} from "./journeyProgress";
import { useFirstCalibrationJourney } from "./useFirstCalibrationJourney";
import { useFirstCalibrationProgress } from "./useFirstCalibrationProgress";

/** Routes where the guide shows its own card instead of the banner. */
const HIDDEN_PATHS = new Set(["/home", "/"]);

function hrefPath(href: string): string {
  return href.split("?")[0];
}

/**
 * Slim, non-blocking strip under the navbar that keeps the first calibration journey in view on
 * every page it passes through. It never opens anything by itself; every move is a link or button.
 */
export function FirstCalibrationBanner() {
  const pathname = usePathname();
  const journey = useFirstCalibrationJourney();
  const active = journey.state?.status === "active" ? journey.state : null;
  const { progress, setup, configSources } = useFirstCalibrationProgress(active);

  if (!active || !progress || HIDDEN_PATHS.has(pathname)) return null;

  const step = journeyStepNumber(progress.stage);
  const stepLabel =
    progress.stage === "done"
      ? "Complete"
      : (JOURNEY_STEPS[step - 1]?.label ?? "First calibration");
  const action = progress.pending ? null : journeyNextAction(active, progress, setup);
  // A link to the page already open would do nothing, except the Chip page, where it opens the
  // Create Chip dialog.
  const showAction =
    action !== null && (progress.stage === "chip" || hrefPath(action.href) !== pathname);
  // On hardware the confirmation comes before the editor and the run, wherever the user is.
  const showReadiness = journeyShowsHardwareReadiness(active, progress, setup);
  const hint = progress.pending
    ? "Checking the guide's records"
    : journeyStageHint(active, progress, setup);

  return (
    <section
      aria-label="First calibration guide"
      className="border-b border-base-content/10 bg-base-200 px-3 py-2 sm:px-4"
    >
      <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
        <div className="flex min-w-0 items-start gap-2">
          {progress.stage === "done" ? (
            <CircleCheck size={16} className="mt-0.5 shrink-0 text-success" aria-hidden="true" />
          ) : progress.issue ? (
            <CircleAlert size={16} className="mt-0.5 shrink-0 text-warning" aria-hidden="true" />
          ) : (
            <GraduationCap
              size={16}
              className="mt-0.5 shrink-0 text-base-content/60"
              aria-hidden="true"
            />
          )}
          <div className="min-w-0">
            <p className="text-sm">
              <span className="font-medium">First calibration</span>
              <span className="text-base-content/60">
                {" "}
                · {progress.stage === "done" ? "" : `Step ${step} of ${JOURNEY_STEPS.length} · `}
                {stepLabel}
              </span>
            </p>
            <p className="break-words text-xs text-base-content/60" role="status">
              {hint}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2">
          {showAction && action && (
            <Link
              href={action.href}
              className="btn btn-primary btn-sm"
              data-coachmark="journey-action"
            >
              {action.label}
            </Link>
          )}
          {progress.issue?.kind === "runFailed" ||
          progress.issue?.kind === "runCancelled" ||
          progress.issue?.kind === "noResults"
            ? active.chipId &&
              active.executionId && (
                <Link
                  href={executionHref(active.chipId, active.executionId)}
                  className="btn btn-ghost btn-sm"
                >
                  Open the run
                </Link>
              )
            : null}
          {progress.stage === "done" ? (
            <button type="button" className="btn btn-ghost btn-sm" onClick={journey.reset}>
              Finish guide
            </button>
          ) : (
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              onClick={() => journey.record({ type: "pause" })}
            >
              Exit guide
            </button>
          )}
        </div>
      </div>
      {showReadiness && active.chipId && (
        <div className="mt-2 md:pl-6" data-coachmark="hardware-readiness">
          <HardwareReadinessCheck
            chipId={active.chipId}
            configSources={configSources}
            confirmed={active.hardwareConfirmedChipId === active.chipId}
            onConfirmedChange={(confirmed) =>
              active.chipId &&
              journey.record({
                type: "hardwareConfirmed",
                chipId: active.chipId,
                confirmed,
              })
            }
          />
        </div>
      )}
    </section>
  );
}
