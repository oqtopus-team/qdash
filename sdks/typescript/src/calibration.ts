/**
 * Calibration definitions: pure builders for the pipeline spec (version 2), the TypeScript
 * counterpart of the Python `qdash.calibration` module.
 *
 * Every builder takes the spec's own snake_case fields, the same names the Python classes take
 * as keyword arguments, checks what can be checked without QDash (field names, types, patterns,
 * enums, bounds, duplicates, and the rules between fields of one step) and returns the spec's
 * JSON with only the fields that were given. A field that is `undefined` or absent is unset and
 * left out; a field given its default value or `null` is written as given, like the Python
 * classes' `exclude_unset` serialization. Targets follow the Python targets and leave out an
 * empty `exclude_qids`. Checks that need the chip, the task catalog or the whole pipeline are
 * the server's: validate a spec with `Pipelines.validate` or the `qdash_plan_pipeline` tool.
 *
 * This module sends nothing and imports nothing at runtime, so it is also published on its own
 * as `@oqtopus-team/qdash-sdk/calibration`. The builders are created by one self-contained
 * function, so a sandbox that cannot import modules (QDash's Code Mode scripts) evaluates the
 * same implementation from {@link calibrationDefinitionsSource}.
 */
import type { QDashApi } from "./_generated/index.js";
import type { CalibrationPipelineSpec, CalibrationPipelineSpecStepsItem, PipelineTargets, TaskCall } from "./types.js";

/** Spec format version the builders write. */
export type SpecVersion = 2;

/** Every built-in step type, by its spec `type`. */
export type CalibrationStepType =
  | "ConfigureAll"
  | "BringUp"
  | "OneQubitCheck"
  | "OneQubitFineTune"
  | "CustomOneQubit"
  | "FilterByStatus"
  | "FilterByMetric"
  | "GenerateCRSchedule"
  | "TwoQubitCalibration"
  | "CustomTwoQubit";

/** Modes of `BringUp`; it has no manual rounds. */
export type OneQubitExecutionMode = "parallel_by_round" | "parallel_by_mux" | "simultaneous_spectroscopy" | "sequential";
/** Modes of `OneQubitCheck`, `OneQubitFineTune` and `CustomOneQubit`. */
export type OneQubitStepExecutionMode = OneQubitExecutionMode | "manual";
/** Modes of `TwoQubitCalibration` and `CustomTwoQubit`. */
export type TwoQubitExecutionMode = "automatic" | "manual";

/** A swept run parameter in the spec's wire format; the worker expands it. */
export interface SweepDeclaration {
  value: number[];
  value_type: "list" | "np.linspace" | "np.logspace" | "np.arange" | "range";
}

/** Sweep declarations, constructor for constructor as Python's `qdash.calibration.sweep`. */
export interface SweepBuilders {
  /** Explicit points: `{ value: [p0, p1, ...], value_type: "list" }`. */
  values(...points: number[]): SweepDeclaration;
  /** `numpy.linspace(start, stop, num)`. */
  linspace(start: number, stop: number, num: number): SweepDeclaration;
  /** `numpy.logspace(start, stop, num)`; `start` and `stop` are base-10 exponents. */
  logspace(start: number, stop: number, num: number): SweepDeclaration;
  /** `numpy.arange(start, stop, step)`. */
  arange(start: number, stop: number, step: number): SweepDeclaration;
  /** Python `range(start, stop, step)`. */
  range(start: number, stop: number, step: number): SweepDeclaration;
}

/** The fields of one task call; `name` is the registered task name. */
export type TaskCallFields = TaskCall;
export type ConfigureAllFields = QDashApi.ConfigureAllStep;
export type BringUpFields = QDashApi.BringUpStep;
export type OneQubitCheckFields = QDashApi.OneQubitCheckStep;
export type OneQubitFineTuneFields = QDashApi.OneQubitFineTuneStep;
export type CustomOneQubitFields = QDashApi.CustomOneQubitStep;
export type FilterByStatusFields = QDashApi.FilterByStatusStep;
export type FilterByMetricFields = QDashApi.FilterByMetricStep;
export type GenerateCRScheduleFields = QDashApi.GenerateCrScheduleStep;
export type TwoQubitCalibrationFields = QDashApi.TwoQubitCalibrationStep;
export type CustomTwoQubitFields = QDashApi.CustomTwoQubitStep;

/** Fields of each step type, by its spec `type`. */
export interface CalibrationStepFields {
  ConfigureAll: ConfigureAllFields;
  BringUp: BringUpFields;
  OneQubitCheck: OneQubitCheckFields;
  OneQubitFineTune: OneQubitFineTuneFields;
  CustomOneQubit: CustomOneQubitFields;
  FilterByStatus: FilterByStatusFields;
  FilterByMetric: FilterByMetricFields;
  GenerateCRSchedule: GenerateCRScheduleFields;
  TwoQubitCalibration: TwoQubitCalibrationFields;
  CustomTwoQubit: CustomTwoQubitFields;
}

/** A step's JSON, with its `type`, by its spec `type`. */
export type CalibrationStep<T extends CalibrationStepType = CalibrationStepType> = Extract<
  CalibrationPipelineSpecStepsItem,
  { type: T }
>;

/** Top-level spec fields a calibration may set; the server defaults the rest. */
export interface CalibrationOptions {
  /** The execution's display name. */
  name?: string;
  /** Run parameters every task call starts from, e.g. shots or interval. */
  defaultRunParameters?: Record<string, unknown>;
  /** The same as `defaultRunParameters`, under the spec's own name; give one of the two. */
  default_run_parameters?: Record<string, unknown>;
  tags?: string[];
  /** Defaults to the configured backend. Not part of the spec; the session methods send it. */
  backendName?: string;
}

/** Options of {@link muxTargets}. */
export interface MuxTargetOptions {
  /** Qubits of the MUXes to leave out. */
  excludeQids?: readonly string[];
  /** The same as `excludeQids`, under the spec's own name; give one of the two. */
  exclude_qids?: readonly string[];
}

/** Every builder, as the module exports them and as `qdash.calibration` in a Code Mode script. */
export interface CalibrationDefinitions {
  readonly SPEC_VERSION: SpecVersion;
  /** Every built-in step type, in the order the Python `STEP_TYPES` lists them. */
  readonly STEP_TYPES: readonly CalibrationStepType[];
  readonly sweep: SweepBuilders;
  /** One task call: `taskCall("CheckT1", { run })` or `taskCall({ name: "CheckT1", run })`. */
  taskCall(name: string, fields?: Omit<TaskCallFields, "name">): TaskCall;
  taskCall(fields: TaskCallFields): TaskCall;
  /** Explicit target qubits by the IDs QDash lists: `{ qids: [...] }`. */
  qubitTargets(qids: readonly string[]): PipelineTargets;
  /** Every qubit of the given MUXes: `{ mux_ids: [...], exclude_qids?: [...] }`. */
  muxTargets(muxIds: readonly number[], options?: MuxTargetOptions): PipelineTargets;
  /** Directed coupling pairs `[control, target]`: `{ pairs: [[control, target], ...] }`. */
  couplingTargets(pairs: readonly (readonly [string, string] | readonly string[])[]): PipelineTargets;
  configureAll(fields?: ConfigureAllFields): CalibrationStep<"ConfigureAll">;
  bringUp(fields?: BringUpFields): CalibrationStep<"BringUp">;
  oneQubitCheck(fields?: OneQubitCheckFields): CalibrationStep<"OneQubitCheck">;
  oneQubitFineTune(fields?: OneQubitFineTuneFields): CalibrationStep<"OneQubitFineTune">;
  customOneQubit(fields: CustomOneQubitFields): CalibrationStep<"CustomOneQubit">;
  filterByStatus(fields?: FilterByStatusFields): CalibrationStep<"FilterByStatus">;
  filterByMetric(fields: FilterByMetricFields): CalibrationStep<"FilterByMetric">;
  generateCRSchedule(fields?: GenerateCRScheduleFields): CalibrationStep<"GenerateCRSchedule">;
  twoQubitCalibration(fields?: TwoQubitCalibrationFields): CalibrationStep<"TwoQubitCalibration">;
  customTwoQubit(fields: CustomTwoQubitFields): CalibrationStep<"CustomTwoQubit">;
  /** A step by its spec `type`, e.g. `calibrationStep("FilterByStatus", { step: "t1" })`. */
  calibrationStep<T extends CalibrationStepType>(type: T, fields?: CalibrationStepFields[T]): CalibrationStep<T>;
  /** The spec version 2 object for `targets` and `steps`, with only the options given. */
  calibrationSpec(
    targets: PipelineTargets,
    steps: readonly CalibrationPipelineSpecStepsItem[],
    options?: CalibrationOptions,
  ): CalibrationPipelineSpec;
}

/**
 * Creates the builders. It must stay self-contained: no reference to anything outside its own
 * body (imports, module constants, helpers), no class, and nothing a transpiler would replace
 * with a helper, because {@link calibrationDefinitionsSource} evaluates its source on its own.
 */
function createCalibrationDefinitions(): CalibrationDefinitions {
  const STEP_ID_PATTERN = /^[a-z][a-z0-9_]{0,63}$/;
  const TASK_NAME_PATTERN = /^[A-Za-z][A-Za-z0-9_]{0,127}$/;
  const CALL_ID_PATTERN = /^[A-Za-z][A-Za-z0-9_.-]{0,63}$/;
  const ONE_QUBIT_MODES = ["parallel_by_round", "parallel_by_mux", "simultaneous_spectroscopy", "sequential"];
  const ONE_QUBIT_STEP_MODES = [...ONE_QUBIT_MODES, "manual"];
  const TWO_QUBIT_MODES = ["automatic", "manual"];
  const ON_FAILURE = ["continue", "stop"];
  // Sweeps this module made, so `input` can refuse them as the Python TaskCall does.
  const sweeps = new WeakSet<object>();

  type Fields = Record<string, unknown>;
  type Check = (owner: string, key: string, value: unknown) => unknown;
  type FieldRule = { check: Check; nullable?: boolean; required?: boolean };

  const show = (value: unknown): string => {
    if (typeof value === "string") return JSON.stringify(value);
    try {
      const text = JSON.stringify(value);
      return text === undefined ? String(value) : text.length > 80 ? `${text.slice(0, 77)}...` : text;
    } catch {
      return String(value);
    }
  };
  const isRecord = (value: unknown): value is Fields =>
    typeof value === "object" && value !== null && !Array.isArray(value);
  const fail = (owner: string, message: string, kind: "type" | "value" = "value"): never => {
    const text = `${owner}: ${message}`;
    throw kind === "type" ? new TypeError(text) : new RangeError(text);
  };

  const string = (pattern?: RegExp, minLength = 0): Check => (owner, key, value) => {
    if (typeof value !== "string") return fail(owner, `${key} must be a string, got ${show(value)}`, "type");
    if (value.length < minLength) return fail(owner, `${key} must not be empty`);
    if (pattern && !pattern.test(value)) return fail(owner, `${key} ${show(value)} must match ${pattern.source}`);
    return value;
  };
  const boolean: Check = (owner, key, value) =>
    typeof value === "boolean" ? value : fail(owner, `${key} must be true or false, got ${show(value)}`, "type");
  const finite: Check = (owner, key, value) =>
    typeof value === "number" && Number.isFinite(value)
      ? value
      : fail(owner, `${key} must be a finite number, got ${show(value)}`, "type");
  const integer = (min?: number, max?: number): Check => (owner, key, value) => {
    if (typeof value !== "number" || !Number.isInteger(value)) {
      return fail(owner, `${key} must be an integer, got ${show(value)}`, "type");
    }
    if ((min !== undefined && value < min) || (max !== undefined && value > max)) {
      return fail(owner, `${key} must be between ${min} and ${max}, got ${value}`);
    }
    return value;
  };
  const oneOf = (choices: readonly string[]): Check => (owner, key, value) =>
    typeof value === "string" && choices.includes(value)
      ? value
      : fail(owner, `${key} must be one of ${choices.map((choice) => show(choice)).join(", ")}, got ${show(value)}`);
  const list = (item: Check, minLength = 0): Check => (owner, key, value) => {
    if (!Array.isArray(value)) return fail(owner, `${key} must be a list, got ${show(value)}`, "type");
    if (value.length < minLength) return fail(owner, `${key} needs at least ${minLength} entr${minLength === 1 ? "y" : "ies"}`);
    return value.map((entry, index) => item(owner, `${key}[${index}]`, entry));
  };
  const mapping: Check = (owner, key, value) => {
    if (!isRecord(value)) return fail(owner, `${key} must be an object of names to values, got ${show(value)}`, "type");
    return { ...value };
  };
  const unique = (owner: string, key: string, values: readonly unknown[]): void => {
    const seen = new Set(values.map((value) => (Array.isArray(value) ? JSON.stringify(value) : value)));
    if (seen.size !== values.length) fail(owner, `${key} contains duplicates`);
  };
  const pair: Check = (owner, key, value) => {
    const entries = list(string())(owner, key, value) as string[];
    if (entries.length !== 2) fail(owner, `${key} must be a [control, target] pair, got ${show(value)}`);
    return entries;
  };

  /** The given fields checked against `rules`; undefined fields are unset and left out. */
  const readFields = (owner: string, value: unknown, rules: Record<string, FieldRule>): Fields => {
    if (value === undefined) value = {};
    if (!isRecord(value)) return fail(owner, `takes an object of fields, got ${show(value)}`, "type");
    const out: Fields = {};
    for (const key of Object.keys(value)) {
      const given = value[key];
      if (given === undefined) continue;
      const rule = rules[key];
      if (rule === undefined) {
        return fail(owner, `has no field ${show(key)}; its fields are ${Object.keys(rules).join(", ")}`, "type");
      }
      if (given === null) {
        if (!rule.nullable) return fail(owner, `${key} must not be null`, "type");
        out[key] = null;
      } else {
        out[key] = rule.check(owner, key, given);
      }
    }
    for (const [key, rule] of Object.entries(rules)) {
      if (rule.required && !(key in out)) fail(owner, `needs ${key}`, "type");
    }
    return out;
  };

  // ---- task calls ---------------------------------------------------------------------------

  const runValues: Check = (owner, key, value) => mapping(owner, key, value);
  const inputValues: Check = (owner, key, value) => {
    const entries = mapping(owner, key, value) as Fields;
    for (const [name, entry] of Object.entries(entries)) {
      if (typeof entry === "object" && entry !== null && sweeps.has(entry)) {
        fail(owner, `input[${show(name)}] uses a sweep; put generated experiment ranges under run`);
      }
    }
    return entries;
  };
  const TASK_CALL_RULES: Record<string, FieldRule> = {
    name: { check: string(TASK_NAME_PATTERN), required: true },
    call_id: { check: string(CALL_ID_PATTERN), nullable: true },
    run: { check: runValues, nullable: true },
    input: { check: inputValues, nullable: true },
    update_calibration_parameters: { check: boolean, nullable: true },
    on_failure: { check: oneOf(ON_FAILURE), nullable: true },
  };
  const readTaskCall = (owner: string, value: unknown): Fields => readFields(owner, value, TASK_CALL_RULES);

  function taskCall(nameOrFields: unknown, more?: unknown): TaskCall {
    if (typeof nameOrFields === "string") {
      if (more !== undefined && !isRecord(more)) fail("taskCall", `takes an object of fields after the name, got ${show(more)}`, "type");
      if (isRecord(more) && more.name !== undefined) fail("taskCall", "takes the name once: as the first argument or as name", "type");
      return readTaskCall("taskCall", { name: nameOrFields, ...(more ?? {}) }) as unknown as TaskCall;
    }
    if (more !== undefined) fail("taskCall", "takes either a task name and fields or one object of fields", "type");
    return readTaskCall("taskCall", nameOrFields) as unknown as TaskCall;
  }

  const calls = (minLength: number): Check => (owner, key, value) => {
    if (typeof value === "string" || !Array.isArray(value)) {
      return fail(owner, `${key} must be a list of task calls, got ${show(value)}`, "type");
    }
    if (value.length < minLength) return fail(owner, `${key} needs at least ${minLength} task call`);
    return value.map((entry, index) => {
      if (typeof entry === "string") {
        return fail(owner, `${key}[${index}] is the task name ${show(entry)}; write it as taskCall(${show(entry)})`, "type");
      }
      return readTaskCall(`${owner} ${key}[${index}]`, entry);
    });
  };

  // ---- targets ------------------------------------------------------------------------------

  function qubitTargets(qids: unknown): PipelineTargets {
    if (typeof qids === "string" || !Array.isArray(qids)) {
      return fail("qubitTargets", `takes a list of qubit IDs, e.g. qubitTargets(["0", "1"]), got ${show(qids)}`, "type");
    }
    const values = list(string(), 1)("qubitTargets", "qids", qids) as string[];
    unique("qubitTargets", "qids", values);
    return { qids: values };
  }

  function muxTargets(muxIds: unknown, options?: unknown): PipelineTargets {
    if (options !== undefined && !isRecord(options)) fail("muxTargets", `options must be an object, got ${show(options)}`, "type");
    const given = (options ?? {}) as Fields;
    for (const key of Object.keys(given)) {
      if (given[key] !== undefined && key !== "excludeQids" && key !== "exclude_qids") {
        fail("muxTargets", `has no option ${show(key)}; its option is excludeQids`, "type");
      }
    }
    if (given.excludeQids !== undefined && given.exclude_qids !== undefined) {
      fail("muxTargets", "takes excludeQids or exclude_qids, not both", "type");
    }
    const ids = list(integer(), 1)("muxTargets", "muxIds", muxIds) as number[];
    unique("muxTargets", "muxIds", ids);
    const excluded = list(string())("muxTargets", "excludeQids", given.excludeQids ?? given.exclude_qids ?? []) as string[];
    // As the Python MuxTargets: an empty exclude_qids is the default and is left out.
    return excluded.length > 0 ? { mux_ids: ids, exclude_qids: excluded } : { mux_ids: ids };
  }

  function couplingTargets(pairs: unknown): PipelineTargets {
    const values = list(pair, 1)("couplingTargets", "pairs", pairs) as [string, string][];
    for (const [control, target] of values) {
      if (control === target) fail("couplingTargets", `pair [${show(control)}, ${show(target)}] couples a qubit with itself`);
    }
    unique("couplingTargets", "pairs", values);
    return { pairs: values };
  }

  // ---- steps --------------------------------------------------------------------------------

  const stepId: FieldRule = { check: string(STEP_ID_PATTERN), nullable: true };
  const qubitRounds: FieldRule = { check: list(list(string())), nullable: true };
  const pairRounds: FieldRule = { check: list(list(pair)), nullable: true };
  const optionalCalls: FieldRule = { check: calls(0), nullable: true };
  const requiredCalls: FieldRule = { check: calls(1), required: true };
  const flag: FieldRule = { check: boolean };

  const checkRounds = (owner: string, label: string, fields: Fields, defaultMode: string): void => {
    const mode = (fields.execution_mode as string | undefined) ?? defaultMode;
    const rounds = fields.rounds ?? null;
    if (mode === "manual" && rounds === null) fail(owner, `${label}: execution_mode "manual" needs rounds`);
    if (mode !== "manual" && rounds !== null) fail(owner, `${label}: rounds need execution_mode "manual"`);
  };
  const checkPairRounds = (owner: string, label: string, fields: Fields): void => {
    checkRounds(owner, label, fields, "automatic");
    const mode = (fields.execution_mode as string | undefined) ?? "automatic";
    if (mode === "manual" && fields.max_parallel_ops !== undefined && fields.max_parallel_ops !== null) {
      fail(owner, `${label}: max_parallel_ops only caps automatic groups; remove it with manual rounds`);
    }
  };
  const checkReference = (owner: string, type: string, fields: Fields): void => {
    if (fields.call_id !== undefined && fields.call_id !== null && (fields.step === undefined || fields.step === null)) {
      fail(owner, `${type}: call_id requires step`);
    }
  };

  type StepRule = { rules: Record<string, FieldRule>; check?: (owner: string, fields: Fields) => void };
  const oneQubitStep = (type: string): StepRule => ({
    rules: {
      step_id: stepId,
      execution_mode: { check: oneOf(ONE_QUBIT_STEP_MODES) },
      rounds: qubitRounds,
      tasks: optionalCalls,
      configure: flag,
    },
    check: (owner, fields) => checkRounds(owner, type, fields, "parallel_by_round"),
  });
  const reference = (type: string, extra: Record<string, FieldRule> = {}): StepRule => ({
    rules: { step: stepId, call_id: { check: string(CALL_ID_PATTERN), nullable: true }, ...extra },
    check: (owner, fields) => checkReference(owner, type, fields),
  });
  const twoQubitFields: Record<string, FieldRule> = {
    execution_mode: { check: oneOf(TWO_QUBIT_MODES) },
    rounds: pairRounds,
    max_parallel_ops: { check: integer(1, 100), nullable: true },
  };

  const STEPS: Record<string, StepRule> = {
    ConfigureAll: {
      rules: {
        step_id: stepId,
        mux_ids: { check: list(integer()), nullable: true },
        call: { check: (owner, key, value) => readTaskCall(`${owner} ${key}`, value), nullable: true },
      },
      check: (owner, fields) => {
        const call = fields.call as Fields | null | undefined;
        if (call && call.name !== "ConfigureAll") {
          fail(owner, `a ConfigureAll step's call must name ConfigureAll, got ${show(call.name)}`);
        }
      },
    },
    BringUp: {
      rules: { step_id: stepId, tasks: optionalCalls, execution_mode: { check: oneOf(ONE_QUBIT_MODES) } },
    },
    OneQubitCheck: oneQubitStep("OneQubitCheck"),
    OneQubitFineTune: oneQubitStep("OneQubitFineTune"),
    CustomOneQubit: {
      rules: {
        step_name: { check: string(STEP_ID_PATTERN) },
        tasks: requiredCalls,
        execution_mode: { check: oneOf(ONE_QUBIT_STEP_MODES) },
        rounds: qubitRounds,
        continue_on_failure: flag,
      },
      check: (owner, fields) =>
        checkRounds(owner, (fields.step_name as string | undefined) ?? "custom_one_qubit", fields, "parallel_by_round"),
    },
    FilterByStatus: reference("FilterByStatus"),
    FilterByMetric: reference("FilterByMetric", {
      metric: { check: string(undefined, 1), required: true },
      threshold: { check: finite, required: true },
    }),
    GenerateCRSchedule: {
      rules: { max_parallel_ops: { check: integer(1, 100) }, inverse: flag },
    },
    TwoQubitCalibration: {
      rules: { ...twoQubitFields, step_id: stepId, tasks: optionalCalls },
      check: (owner, fields) => checkPairRounds(owner, "TwoQubitCalibration", fields),
    },
    CustomTwoQubit: {
      rules: {
        ...twoQubitFields,
        step_name: { check: string(STEP_ID_PATTERN) },
        tasks: requiredCalls,
        continue_on_failure: flag,
      },
      check: (owner, fields) => checkPairRounds(owner, (fields.step_name as string | undefined) ?? "custom_two_qubit", fields),
    },
  };
  const STEP_TYPES = Object.keys(STEPS) as CalibrationStepType[];
  const builderName = (type: string): string =>
    type === "GenerateCRSchedule" ? "generateCRSchedule" : type.charAt(0).toLowerCase() + type.slice(1);

  function buildStep(owner: string, type: string, fields: unknown): CalibrationPipelineSpecStepsItem {
    const step = STEPS[type];
    if (step === undefined) {
      return fail("calibrationStep", `unknown step type ${show(type)}; the types are ${STEP_TYPES.join(", ")}`);
    }
    if (isRecord(fields) && fields.type !== undefined) {
      fail(owner, "sets the step type itself; leave out type", "type");
    }
    const out = readFields(owner, fields, step.rules);
    step.check?.(owner, out);
    return { type, ...out } as unknown as CalibrationPipelineSpecStepsItem;
  }
  const stepBuilder = (type: string) => (fields?: unknown) => buildStep(builderName(type), type, fields);

  function calibrationStep(type: unknown, fields?: unknown): CalibrationPipelineSpecStepsItem {
    if (typeof type !== "string") return fail("calibrationStep", `takes a step type name first, got ${show(type)}`, "type");
    return buildStep(`calibrationStep(${show(type)})`, type, fields);
  }

  // ---- spec ---------------------------------------------------------------------------------

  function calibrationSpec(targets: unknown, steps: unknown, options?: unknown): CalibrationPipelineSpec {
    if (!isRecord(targets)) fail("calibrationSpec", `targets must be an object such as qubitTargets([...]), got ${show(targets)}`, "type");
    if (typeof steps === "string" || !Array.isArray(steps)) fail("calibrationSpec", "steps must be a list of steps", "type");
    if (options !== undefined && !isRecord(options)) fail("calibrationSpec", `options must be an object, got ${show(options)}`, "type");
    const given = (options ?? {}) as Fields;
    const known = ["name", "defaultRunParameters", "default_run_parameters", "tags", "backendName"];
    for (const key of Object.keys(given)) {
      if (given[key] !== undefined && !known.includes(key)) {
        fail("calibrationSpec", `has no option ${show(key)}; its options are name, defaultRunParameters, tags`, "type");
      }
    }
    if (given.defaultRunParameters !== undefined && given.default_run_parameters !== undefined) {
      fail("calibrationSpec", "takes defaultRunParameters or default_run_parameters, not both", "type");
    }
    const defaults = given.defaultRunParameters ?? given.default_run_parameters;
    if (given.name !== undefined && typeof given.name !== "string") fail("calibrationSpec", "name must be a string", "type");
    return {
      spec_version: 2,
      ...(given.name !== undefined ? { name: given.name as string } : {}),
      targets: targets as PipelineTargets,
      steps: [...(steps as CalibrationPipelineSpecStepsItem[])],
      ...(defaults !== undefined ? { default_run_parameters: mapping("calibrationSpec", "defaultRunParameters", defaults) as Fields } : {}),
      ...(given.tags !== undefined ? { tags: list(string())("calibrationSpec", "tags", given.tags) as string[] } : {}),
    };
  }

  // ---- sweeps -------------------------------------------------------------------------------

  const declare = (value: number[], valueType: SweepDeclaration["value_type"]): SweepDeclaration => {
    const declaration: SweepDeclaration = { value, value_type: valueType };
    sweeps.add(declaration);
    return declaration;
  };
  const number = (constructor: string, name: string, value: unknown): void => {
    if (typeof value !== "number" || !Number.isFinite(value)) {
      throw new TypeError(`sweep.${constructor} ${name} must be a finite number, got ${String(value)}`);
    }
  };
  const count = (constructor: string, num: unknown): void => {
    if (typeof num !== "number" || !Number.isInteger(num) || num < 1) {
      throw new RangeError(`sweep.${constructor} num must be a positive integer, got ${String(num)}`);
    }
  };
  const sweep: SweepBuilders = Object.freeze({
    values(...points: number[]): SweepDeclaration {
      if (points.length === 0) throw new RangeError("sweep.values needs at least one point");
      points.forEach((point, index) => number("values", `points[${index}]`, point));
      return declare(points, "list");
    },
    linspace(start: number, stop: number, num: number): SweepDeclaration {
      number("linspace", "start", start);
      number("linspace", "stop", stop);
      count("linspace", num);
      return declare([start, stop, num], "np.linspace");
    },
    logspace(start: number, stop: number, num: number): SweepDeclaration {
      number("logspace", "start", start);
      number("logspace", "stop", stop);
      count("logspace", num);
      return declare([start, stop, num], "np.logspace");
    },
    arange(start: number, stop: number, step: number): SweepDeclaration {
      number("arange", "start", start);
      number("arange", "stop", stop);
      number("arange", "step", step);
      if (step === 0) throw new RangeError("sweep.arange step must not be zero");
      return declare([start, stop, step], "np.arange");
    },
    range(start: number, stop: number, step: number): SweepDeclaration {
      for (const [name, value] of [
        ["start", start],
        ["stop", stop],
        ["step", step],
      ] as const) {
        if (!Number.isInteger(value)) throw new TypeError(`sweep.range ${name} must be an integer, got ${String(value)}`);
      }
      if (step === 0) throw new RangeError("sweep.range step must not be zero");
      return declare([start, stop, step], "range");
    },
  });

  return Object.freeze({
    SPEC_VERSION: 2,
    STEP_TYPES: Object.freeze([...STEP_TYPES]),
    sweep,
    taskCall,
    qubitTargets,
    muxTargets,
    couplingTargets,
    configureAll: stepBuilder("ConfigureAll"),
    bringUp: stepBuilder("BringUp"),
    oneQubitCheck: stepBuilder("OneQubitCheck"),
    oneQubitFineTune: stepBuilder("OneQubitFineTune"),
    customOneQubit: stepBuilder("CustomOneQubit"),
    filterByStatus: stepBuilder("FilterByStatus"),
    filterByMetric: stepBuilder("FilterByMetric"),
    generateCRSchedule: stepBuilder("GenerateCRSchedule"),
    twoQubitCalibration: stepBuilder("TwoQubitCalibration"),
    customTwoQubit: stepBuilder("CustomTwoQubit"),
    calibrationStep,
    calibrationSpec,
  }) as unknown as CalibrationDefinitions;
}

const definitions = createCalibrationDefinitions();

export const SPEC_VERSION: SpecVersion = definitions.SPEC_VERSION;
export const STEP_TYPES: readonly CalibrationStepType[] = definitions.STEP_TYPES;
export const sweep: SweepBuilders = definitions.sweep;
export const taskCall: CalibrationDefinitions["taskCall"] = definitions.taskCall;
export const qubitTargets: CalibrationDefinitions["qubitTargets"] = definitions.qubitTargets;
export const muxTargets: CalibrationDefinitions["muxTargets"] = definitions.muxTargets;
export const couplingTargets: CalibrationDefinitions["couplingTargets"] = definitions.couplingTargets;
export const configureAll: CalibrationDefinitions["configureAll"] = definitions.configureAll;
export const bringUp: CalibrationDefinitions["bringUp"] = definitions.bringUp;
export const oneQubitCheck: CalibrationDefinitions["oneQubitCheck"] = definitions.oneQubitCheck;
export const oneQubitFineTune: CalibrationDefinitions["oneQubitFineTune"] = definitions.oneQubitFineTune;
export const customOneQubit: CalibrationDefinitions["customOneQubit"] = definitions.customOneQubit;
export const filterByStatus: CalibrationDefinitions["filterByStatus"] = definitions.filterByStatus;
export const filterByMetric: CalibrationDefinitions["filterByMetric"] = definitions.filterByMetric;
export const generateCRSchedule: CalibrationDefinitions["generateCRSchedule"] = definitions.generateCRSchedule;
export const twoQubitCalibration: CalibrationDefinitions["twoQubitCalibration"] = definitions.twoQubitCalibration;
export const customTwoQubit: CalibrationDefinitions["customTwoQubit"] = definitions.customTwoQubit;
export const calibrationStep: CalibrationDefinitions["calibrationStep"] = definitions.calibrationStep;
export const calibrationSpec: CalibrationDefinitions["calibrationSpec"] = definitions.calibrationSpec;

/**
 * JavaScript source of an expression that evaluates to a new, frozen set of these builders,
 * the same implementation this module exports. It references nothing outside itself, so a
 * sandbox without module imports can evaluate it (`(0, eval)(source)`); it reads no globals
 * beyond the language's own and has no side effects.
 */
export function calibrationDefinitionsSource(): string {
  return `(${createCalibrationDefinitions.toString()})()`;
}
