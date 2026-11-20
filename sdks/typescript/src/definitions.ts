/**
 * Small builders for the generated pipeline spec types.
 *
 * Targets, steps and task calls are the API's own generated types
 * (`PipelineTargets`, `CustomOneQubitStep`, `TaskCall`, ...), written in the
 * spec's JSON form with its snake_case keys; object literals of those types are
 * always accepted. These helpers only fill in what is tedious to write: the
 * target shape, a step's `type` and sweep declarations. They send nothing, and
 * leave every rule beyond the obvious shape to the server's validate route.
 */
import type {
  CalibrationPipelineSpec,
  CalibrationPipelineSpecStepsItem,
  CustomOneQubitStep,
  PipelineTargets,
} from "@oqtopus-team/qdash-client/models";

/** Explicit target qubits by the IDs QDash lists: `{ qids: [...] }`. */
export function qubitTargets(qids: readonly string[]): PipelineTargets {
  if (typeof qids === "string" || !Array.isArray(qids)) {
    throw new TypeError('qubitTargets takes a list of qubit IDs, e.g. qubitTargets(["0", "1"])');
  }
  return { qids: [...qids] };
}

/** Every qubit of the given MUXes: `{ mux_ids: [...], exclude_qids?: [...] }`. */
export function muxTargets(
  muxIds: readonly number[],
  options: { excludeQids?: readonly string[] } = {},
): PipelineTargets {
  for (const [name, value] of [
    ["muxIds", muxIds],
    ["excludeQids", options.excludeQids ?? []],
  ] as const) {
    if (!Array.isArray(value)) throw new TypeError(`muxTargets ${name} must be a list`);
  }
  const excluded = [...(options.excludeQids ?? [])];
  return excluded.length > 0 ? { mux_ids: [...muxIds], exclude_qids: excluded } : { mux_ids: [...muxIds] };
}

/** A `CustomOneQubit` step: its task calls, in order, on every candidate qubit. */
export function customOneQubit(step: Omit<CustomOneQubitStep, "type">): CustomOneQubitStep {
  return { type: "CustomOneQubit", ...step };
}

/** Top-level spec fields a calibration may set; the server defaults the rest. */
export interface CalibrationOptions {
  /** The execution's display name. */
  name?: string;
  /** Run parameters every task call starts from, e.g. shots or interval. */
  defaultRunParameters?: Record<string, unknown>;
  tags?: string[];
  /** Defaults to the configured backend. */
  backendName?: string;
}

/** The spec version 2 object for `targets` and `steps`, with only the options given. */
export function calibrationSpec(
  targets: PipelineTargets,
  steps: readonly CalibrationPipelineSpecStepsItem[],
  options: CalibrationOptions = {},
): CalibrationPipelineSpec {
  return {
    spec_version: 2,
    ...(options.name !== undefined ? { name: options.name } : {}),
    targets,
    steps: [...steps],
    ...(options.defaultRunParameters !== undefined
      ? { default_run_parameters: options.defaultRunParameters }
      : {}),
    ...(options.tags !== undefined ? { tags: options.tags } : {}),
  };
}

/** A swept run parameter in the spec's wire format; the worker expands it. */
export interface SweepDeclaration {
  value: number[];
  value_type: "list" | "np.linspace" | "np.logspace" | "np.arange" | "range";
}

function number(constructor: string, name: string, value: unknown): void {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new TypeError(`sweep.${constructor} ${name} must be a finite number, got ${String(value)}`);
  }
}

function count(constructor: string, num: unknown): void {
  if (typeof num !== "number" || !Number.isInteger(num) || num < 1) {
    throw new RangeError(`sweep.${constructor} num must be a positive integer, got ${String(num)}`);
  }
}

/**
 * Sweep declarations, constructor for constructor as `qdash.workflow.sweep` and
 * the Python SDK write them. Nothing is expanded locally.
 */
export const sweep = {
  /** Explicit points: `{ value: [p0, p1, ...], value_type: "list" }`. */
  values(...points: number[]): SweepDeclaration {
    if (points.length === 0) throw new RangeError("sweep.values needs at least one point");
    points.forEach((point, index) => number("values", `points[${index}]`, point));
    return { value: points, value_type: "list" };
  },
  /** `numpy.linspace(start, stop, num)`. */
  linspace(start: number, stop: number, num: number): SweepDeclaration {
    number("linspace", "start", start);
    number("linspace", "stop", stop);
    count("linspace", num);
    return { value: [start, stop, num], value_type: "np.linspace" };
  },
  /** `numpy.logspace(start, stop, num)`; `start` and `stop` are base-10 exponents. */
  logspace(start: number, stop: number, num: number): SweepDeclaration {
    number("logspace", "start", start);
    number("logspace", "stop", stop);
    count("logspace", num);
    return { value: [start, stop, num], value_type: "np.logspace" };
  },
  /** `numpy.arange(start, stop, step)`. */
  arange(start: number, stop: number, step: number): SweepDeclaration {
    number("arange", "start", start);
    number("arange", "stop", stop);
    number("arange", "step", step);
    if (step === 0) throw new RangeError("sweep.arange step must not be zero");
    return { value: [start, stop, step], value_type: "np.arange" };
  },
  /** Python `range(start, stop, step)`. */
  range(start: number, stop: number, step: number): SweepDeclaration {
    for (const [name, value] of [
      ["start", start],
      ["stop", stop],
      ["step", step],
    ] as const) {
      if (!Number.isInteger(value)) {
        throw new TypeError(`sweep.range ${name} must be an integer, got ${String(value)}`);
      }
    }
    if (step === 0) throw new RangeError("sweep.range step must not be zero");
    return { value: [start, stop, step], value_type: "range" };
  },
} as const;
