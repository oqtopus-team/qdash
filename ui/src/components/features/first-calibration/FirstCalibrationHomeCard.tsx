"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";

import { CircleAlert, CircleCheck } from "lucide-react";

import {
  canCreatePresetChip,
  type ChipSetupMode,
  presetBackendLabel,
} from "@/components/features/chip/chipSetupMode";
import { JOURNEY_CREATE_CHIP_QUERY_VALUE, type JourneyState } from "@/lib/firstCalibrationJourney";
import type { ChipResponse } from "@/schemas";

import { HardwareReadinessCheck } from "./HardwareReadinessCheck";
import { JourneySteps } from "./JourneySteps";
import {
  chipOverviewHref,
  journeyNewFlowHref,
  journeyNextAction,
  journeyShowsHardwareReadiness,
  journeyStageHint,
  journeyStepStates,
  type JourneyProgress,
} from "./journeyProgress";
import { useFirstCalibrationJourney } from "./useFirstCalibrationJourney";
import { useFirstCalibrationProgress, type JourneyChipList } from "./useFirstCalibrationProgress";

const NEW_CHIP = "";
const CREATE_CHIP_HREF = `/chip?journey=${JOURNEY_CREATE_CHIP_QUERY_VALUE}`;

interface FirstCalibrationHomeCardProps {
  /** Whether Home found chips in the project; a project without chips gets the start form. */
  projectHasChips: boolean;
  /** Show the start form even though the project already has chips. */
  startRequested: boolean;
  onStartDismissed: () => void;
}

/**
 * What the chip choice may offer once the deployment and the chip list are known, or why it
 * cannot be offered yet. Nothing is offered while either is unknown, so a preset deployment never
 * gets the hardware path by accident.
 */
type ChipChoiceState =
  | { status: "loading" }
  | { status: "error" }
  | { status: "unavailable"; message: string }
  | { status: "ready"; options: ChipResponse[]; allowCreate: boolean };

/** Chips a first run can use: on a preset backend, only chips the size of its device. */
function eligibleChips(chips: readonly ChipResponse[], setup: ChipSetupMode): ChipResponse[] {
  if (setup.kind === "pending") return [];
  if (setup.kind === "preset" && !setup.preset) return [];
  const sorted = [...chips].sort((a, b) => {
    const dateA = a.installed_at ? new Date(a.installed_at).getTime() : 0;
    const dateB = b.installed_at ? new Date(b.installed_at).getTime() : 0;
    return dateB - dateA;
  });
  if (setup.kind === "preset" && setup.preset) {
    const qubits = setup.preset.n_qubits;
    return sorted.filter((chip) => chip.size === qubits);
  }
  return sorted;
}

function chipChoiceState(setup: ChipSetupMode, chipList: JourneyChipList): ChipChoiceState {
  if ((setup.kind === "pending" && setup.failed) || chipList.status === "error") {
    return { status: "error" };
  }
  if (setup.kind === "pending" || chipList.status === "loading") return { status: "loading" };
  if (setup.kind === "preset" && !setup.preset) {
    return {
      status: "unavailable",
      message: `This deployment runs the ${presetBackendLabel(setup.backend)}, but the API does not offer its device. Ask an administrator to check the API configuration.`,
    };
  }
  const options = eligibleChips(chipList.chips, setup);
  const allowCreate = setup.kind === "hardware" || canCreatePresetChip(setup);
  if (options.length === 0 && !allowCreate) {
    return {
      status: "unavailable",
      message:
        "The virtual device needs the configuration directory, which is not mounted on this deployment. Ask an administrator to mount it.",
    };
  }
  return { status: "ready", options, allowCreate };
}

function ChipChoiceStatus({
  state,
  onRetry,
}: {
  state: Exclude<ChipChoiceState, { status: "ready" }>;
  onRetry: () => void;
}) {
  if (state.status === "loading") {
    return (
      <p className="flex items-center gap-2 text-sm text-base-content/70" role="status">
        <span className="loading loading-spinner loading-sm" aria-hidden="true" />
        Checking this deployment and its chips
      </p>
    );
  }
  if (state.status === "unavailable") {
    return (
      <div role="alert" className="alert alert-warning alert-soft text-sm">
        <CircleAlert size={16} className="shrink-0" aria-hidden="true" />
        <span className="min-w-0 break-words">{state.message}</span>
      </div>
    );
  }
  return (
    <div role="alert" className="alert alert-error alert-soft text-sm sm:alert-horizontal">
      <CircleAlert size={16} className="shrink-0" aria-hidden="true" />
      <span className="min-w-0 break-words">
        QDash could not check how this deployment runs calibrations or which chips it has.
      </span>
      <button type="button" className="btn btn-sm" onClick={onRetry}>
        Try again
      </button>
    </div>
  );
}

function ChipChoice({
  options,
  allowCreate,
  submitLabel,
  onUseChip,
  onCreateChip,
}: {
  options: readonly ChipResponse[];
  allowCreate: boolean;
  submitLabel: string;
  onUseChip: (chipId: string) => void;
  onCreateChip: () => void;
}) {
  const selectId = useId();
  const [choice, setChoice] = useState<string>(() => options[0]?.chip_id ?? NEW_CHIP);
  // "Create a new chip" stays chosen; a chosen chip that left the list falls back to the first.
  const selected =
    (choice === NEW_CHIP && allowCreate) || options.some((chip) => chip.chip_id === choice)
      ? choice
      : (options[0]?.chip_id ?? NEW_CHIP);

  return (
    <form
      className="flex flex-col gap-2 sm:flex-row sm:items-end"
      onSubmit={(event) => {
        event.preventDefault();
        if (selected === NEW_CHIP) {
          if (allowCreate) onCreateChip();
        } else {
          onUseChip(selected);
        }
      }}
    >
      <div className="min-w-0 flex-1">
        <label htmlFor={selectId} className="mb-1 block text-xs text-base-content/60">
          Chip to calibrate
        </label>
        <select
          id={selectId}
          className="select select-sm w-full"
          value={selected}
          onChange={(event) => setChoice(event.target.value)}
        >
          {options.map((chip) => (
            <option key={chip.chip_id} value={chip.chip_id}>
              {chip.chip_id}
              {chip.size ? ` (${chip.size} qubits)` : ""}
            </option>
          ))}
          {allowCreate && <option value={NEW_CHIP}>Create a new chip</option>}
        </select>
      </div>
      <button type="submit" className="btn btn-primary btn-sm" data-coachmark="journey-action">
        {submitLabel}
      </button>
    </form>
  );
}

function introText(setup: ChipSetupMode): string {
  if (setup.kind === "preset" && setup.preset) {
    if (setup.preset.n_qubits === 1) {
      return "Run a measurement on the emulated qubit and inspect a result, without contacting hardware";
    }
    return `Calibrate the ${setup.preset.n_qubits}-qubit virtual device and inspect a result, without contacting hardware`;
  }
  return "Run a calibration on a chip and inspect a result";
}

/** Frame shared by every state of the Home card; the same surface as the other Home sections. */
function JourneyCard({ busy, children }: { busy?: boolean; children: ReactNode }) {
  return (
    <section
      aria-labelledby="first-calibration-heading"
      aria-busy={busy}
      className="card bg-base-200 shadow-sm"
    >
      <div className="card-body gap-4 p-5">{children}</div>
    </section>
  );
}

/** Title and status on the left, the guide's own quiet controls on the right. */
function JourneyHeader({
  title,
  status,
  controls,
}: {
  title: ReactNode;
  status: ReactNode;
  controls?: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
      <div className="min-w-0">
        <h2
          id="first-calibration-heading"
          className="flex flex-wrap items-center gap-2 text-sm font-medium"
        >
          {title}
        </h2>
        {status}
      </div>
      {controls && <div className="-my-1 flex shrink-0 flex-wrap gap-1">{controls}</div>}
    </div>
  );
}

function CompletedJourney({
  state,
  progress,
  onFinish,
}: {
  state: JourneyState;
  progress: JourneyProgress;
  onFinish: () => void;
}) {
  return (
    <JourneyCard>
      <JourneyHeader
        title={
          <>
            <CircleCheck size={16} className="shrink-0 text-success" aria-hidden="true" />
            First calibration complete
          </>
        }
        status={
          <p className="mt-0.5 break-all font-mono text-xs text-base-content/60">
            {state.chipId}
            {state.flowName ? ` · ${state.flowName}` : ""}
            {state.executionId ? ` · ${state.executionId}` : ""}
          </p>
        }
        controls={
          <button type="button" className="btn btn-ghost btn-sm" onClick={onFinish}>
            Close guide
          </button>
        }
      />
      <div className="flex flex-wrap gap-2">
        {progress.recommendedResult && (
          <Link
            href={`/task-results/${encodeURIComponent(progress.recommendedResult.taskId)}`}
            className="btn btn-sm"
          >
            Open {progress.recommendedResult.name} result
          </Link>
        )}
        {state.chipId && (
          <Link href={chipOverviewHref(state.chipId)} className="btn btn-sm">
            Chip overview
          </Link>
        )}
      </div>
    </JourneyCard>
  );
}

/**
 * Home entry point of the first calibration journey: starts it, shows its stages and resumes it.
 * Progress comes from the chip, flow and execution records the journey points at.
 *
 * A chip can only be chosen once the deployment kind and the project's chips are known. On a preset
 * deployment the choice opens the preset's template; on hardware the guide first asks the user to
 * confirm the chip's configuration here, before it links to the editor or the run.
 */
export function FirstCalibrationHomeCard({
  projectHasChips,
  startRequested,
  onStartDismissed,
}: FirstCalibrationHomeCardProps) {
  const router = useRouter();
  const journey = useFirstCalibrationJourney();
  const { state } = journey;
  // The start form needs the deployment kind too, to offer only chips a first run can use.
  const { progress, setup, configSources, chipList, retrySetup } = useFirstCalibrationProgress(
    state,
    { loadSetup: journey.enabled },
  );
  const choice = chipChoiceState(setup, chipList);
  const readinessRef = useRef<HTMLDivElement>(null);
  const [focusReadiness, setFocusReadiness] = useState(false);
  const showReadiness =
    state !== null && progress !== null && journeyShowsHardwareReadiness(state, progress, setup);

  // After a hardware chip is chosen the guide stays on Home; move focus to what it asks next.
  useEffect(() => {
    if (!focusReadiness || !showReadiness) return;
    readinessRef.current?.focus();
    setFocusReadiness(false);
  }, [focusReadiness, showReadiness]);

  if (!journey.enabled) return null;

  /**
   * Where choosing a chip leads, or null when it must not lead anywhere yet. Checked again here,
   * not only by what the form renders, so a stale form cannot start on an unresolved setup.
   */
  const chipDestination = (chipId: string): { href: string | null } | null => {
    if (choice.status !== "ready") return null;
    if (!choice.options.some((chip) => chip.chip_id === chipId)) return null;
    if (setup.kind === "preset") {
      const href = journeyNewFlowHref(setup, chipId);
      return href ? { href } : null;
    }
    // Hardware: confirm readiness on Home first; the editor link appears once it is confirmed.
    return setup.kind === "hardware" ? { href: null } : null;
  };

  const canCreateChip = choice.status === "ready" && choice.allowCreate;

  const startWithChip = (chipId: string) => {
    const destination = chipDestination(chipId);
    if (!destination) return;
    journey.record({ type: "start", chipId });
    onStartDismissed();
    if (destination.href) router.push(destination.href);
    else setFocusReadiness(true);
  };

  const startWithNewChip = () => {
    if (!canCreateChip) return;
    journey.record({ type: "start", chipId: null });
    onStartDismissed();
    router.push(CREATE_CHIP_HREF);
  };

  if (!state) {
    if (projectHasChips && !startRequested) return null;
    const onlyCreate =
      choice.status === "ready" && choice.options.length === 0 && choice.allowCreate;
    return (
      <JourneyCard busy={choice.status === "loading"}>
        <JourneyHeader
          title="First calibration"
          status={
            <p className="mt-0.5 break-words text-sm text-base-content/60">{introText(setup)}</p>
          }
          controls={
            startRequested && (
              <button type="button" className="btn btn-ghost btn-sm" onClick={onStartDismissed}>
                Not now
              </button>
            )
          }
        />
        <JourneySteps
          states={{
            chip: "current",
            calibration: "upcoming",
            progress: "upcoming",
            result: "upcoming",
            overview: "upcoming",
          }}
        />
        {choice.status !== "ready" ? (
          <ChipChoiceStatus state={choice} onRetry={retrySetup} />
        ) : onlyCreate ? (
          <div>
            <button type="button" className="btn btn-primary btn-sm" onClick={startWithNewChip}>
              Create a chip
            </button>
          </div>
        ) : (
          <ChipChoice
            options={choice.options}
            allowCreate={choice.allowCreate}
            submitLabel="Start"
            onUseChip={startWithChip}
            onCreateChip={startWithNewChip}
          />
        )}
      </JourneyCard>
    );
  }

  if (!progress) return null;
  if (progress.stage === "done") {
    return <CompletedJourney state={state} progress={progress} onFinish={journey.reset} />;
  }

  const paused = state.status === "paused";
  const action = progress.pending ? null : journeyNextAction(state, progress, setup);
  const showChipChoice = progress.stage === "chip";
  const setupFailed = setup.kind === "pending" && setup.failed;

  const go = (href: string) => {
    if (paused) journey.record({ type: "resume" });
    router.push(href);
  };

  const continueWithChip = (chipId: string) => {
    const destination = chipDestination(chipId);
    if (!destination) return;
    journey.record({ type: "chipSelected", chipId });
    if (destination.href) {
      go(destination.href);
    } else {
      if (paused) journey.record({ type: "resume" });
      setFocusReadiness(true);
    }
  };

  const actionLabel = (label: string) => (paused ? `Resume: ${label}` : label);

  return (
    <JourneyCard>
      <JourneyHeader
        title={
          <>
            First calibration
            {paused && <span className="badge badge-sm">Paused</span>}
          </>
        }
        status={
          <>
            <p className="mt-0.5 flex items-start gap-1.5 break-words text-sm" role="status">
              {(progress.issue || setupFailed) && (
                <CircleAlert
                  size={16}
                  className="mt-0.5 shrink-0 text-warning"
                  aria-hidden="true"
                />
              )}
              <span className="min-w-0 text-base-content/60">
                {progress.pending
                  ? "Checking the guide's records"
                  : journeyStageHint(state, progress, setup)}
              </span>
            </p>
            {state.chipId && (
              <p className="mt-1 break-all font-mono text-xs text-base-content/60">
                {state.chipId}
                {state.flowName ? ` · ${state.flowName}` : ""}
                {state.executionId ? ` · ${state.executionId}` : ""}
              </p>
            )}
          </>
        }
        controls={
          <>
            {paused && !action && !showChipChoice && (
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => journey.record({ type: "resume" })}
              >
                Resume
              </button>
            )}
            {!paused && (
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => journey.record({ type: "pause" })}
              >
                Exit guide
              </button>
            )}
            <button type="button" className="btn btn-ghost btn-sm" onClick={journey.reset}>
              Start over
            </button>
          </>
        }
      />

      <JourneySteps states={journeyStepStates(progress)} />

      {showReadiness && state.chipId && (
        <div
          ref={readinessRef}
          tabIndex={-1}
          role="group"
          aria-label={`Hardware readiness of ${state.chipId}`}
          data-coachmark="hardware-readiness"
          className="rounded-box outline-offset-2"
        >
          <HardwareReadinessCheck
            chipId={state.chipId}
            configSources={configSources}
            confirmed={state.hardwareConfirmedChipId === state.chipId}
            onConfirmedChange={(confirmed) =>
              state.chipId &&
              journey.record({
                type: "hardwareConfirmed",
                chipId: state.chipId,
                confirmed,
              })
            }
          />
        </div>
      )}

      {showChipChoice ? (
        choice.status !== "ready" ? (
          <ChipChoiceStatus state={choice} onRetry={retrySetup} />
        ) : choice.options.length === 0 ? (
          <div>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              data-coachmark="journey-action"
              onClick={() => canCreateChip && go(CREATE_CHIP_HREF)}
            >
              {actionLabel("Create a chip")}
            </button>
          </div>
        ) : (
          <ChipChoice
            options={choice.options}
            allowCreate={choice.allowCreate}
            submitLabel={paused ? "Resume" : "Continue"}
            onUseChip={continueWithChip}
            onCreateChip={() => canCreateChip && go(CREATE_CHIP_HREF)}
          />
        )
      ) : setupFailed ? (
        <ChipChoiceStatus state={{ status: "error" }} onRetry={retrySetup} />
      ) : (
        action && (
          <div>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              data-coachmark="journey-action"
              onClick={() => go(action.href)}
            >
              {actionLabel(action.label)}
            </button>
          </div>
        )
      )}
    </JourneyCard>
  );
}
