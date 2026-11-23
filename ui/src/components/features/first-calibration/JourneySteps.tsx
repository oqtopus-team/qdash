import { JOURNEY_STEPS, type JourneyStepState, type JourneyStepId } from "./journeyProgress";

/** Segment above each label; the current step is the only one in the primary color. */
const SEGMENT_CLASS: Record<JourneyStepState, string> = {
  done: "bg-base-content/40",
  current: "bg-primary",
  attention: "bg-warning",
  upcoming: "bg-base-content/10",
};

const LABEL_CLASS: Record<JourneyStepState, string> = {
  done: "text-base-content/60",
  current: "font-medium text-base-content",
  attention: "font-medium text-base-content",
  upcoming: "text-base-content/60",
};

const STEP_STATUS_TEXT: Record<JourneyStepState, string> = {
  done: "done",
  current: "current step",
  attention: "needs attention",
  upcoming: "not started",
};

/** Compact progress of the guide: one thin segment and a short label per step. */
export function JourneySteps({ states }: { states: Record<JourneyStepId, JourneyStepState> }) {
  return (
    <ol className="grid grid-cols-5 gap-1.5" aria-label="First calibration steps">
      {JOURNEY_STEPS.map((step) => {
        const state = states[step.id];
        return (
          <li
            key={step.id}
            className="min-w-0"
            aria-current={state === "current" || state === "attention" ? "step" : undefined}
          >
            <span className={`block h-1 rounded-full ${SEGMENT_CLASS[state]}`} aria-hidden="true" />
            <span className={`mt-1.5 block break-words text-xs ${LABEL_CLASS[state]}`}>
              {step.label}
              <span className="sr-only"> ({STEP_STATUS_TEXT[state]})</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}
