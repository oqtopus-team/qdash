/**
 * Evidence text for pi-qcaleval's `qcal_evaluate`: what a task result's
 * measurement settings were, read from the run parameters QDash records.
 *
 * The evaluation model is meant to read the plot, so the context names the
 * task, the target and the sweep (what was varied, over which range, in how
 * many points), not the fitted results. The numbers come from the recorded
 * parameters, so they are exact and need no hand-written summary.
 */

/** One parameter as QDash records it on a task result. */
export interface RecordedParameter {
  value: unknown;
  unit: string;
  value_type: string;
  description: string;
}

/** A swept parameter: the axis a plot was taken along. */
export interface Sweep {
  name: string;
  unit: string;
  description: string;
  /** How the points are spaced. */
  spacing: "linear" | "log" | "list";
  /** First and last point, in the parameter's unit. */
  start: number;
  stop: number;
  points: number;
  /** Spacing between points for a linear sweep. */
  step?: number;
}

/** The recorded parameters of a task result, as a name → record map. */
export function recordedParameters(value: unknown): Record<string, RecordedParameter> {
  const output: Record<string, RecordedParameter> = {};
  const input = value && typeof value === "object" ? (value as Record<string, unknown>) : {};
  for (const [name, raw] of Object.entries(input)) {
    if (raw && typeof raw === "object" && "value" in raw) {
      const record = raw as Record<string, unknown>;
      output[name] = {
        value: record.value,
        unit: typeof record.unit === "string" ? record.unit : "",
        value_type: typeof record.value_type === "string" ? record.value_type : "",
        description: typeof record.description === "string" ? record.description : "",
      };
    } else if (typeof raw === "number" || typeof raw === "string" || typeof raw === "boolean" || Array.isArray(raw)) {
      output[name] = { value: raw, unit: "", value_type: Array.isArray(raw) ? "list" : typeof raw, description: "" };
    }
  }
  return output;
}

function numbers(value: unknown): number[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const list = value.map((item) => (typeof item === "number" ? item : typeof item === "string" ? Number(item) : Number.NaN));
  return list.length > 0 && list.every((item) => Number.isFinite(item)) ? list : undefined;
}

/**
 * The sweeps among the recorded parameters, in record order, read the way
 * QDash's `get_value` expands them: `range` / `np.arange` as (start, stop,
 * step), `np.linspace` as (start, stop, num), `np.logspace` as (log10 start,
 * log10 stop, num), and `list` as the points themselves.
 */
export function sweepsOf(parameters: Record<string, RecordedParameter>): Sweep[] {
  const sweeps: Sweep[] = [];
  for (const [name, parameter] of Object.entries(parameters)) {
    const values = numbers(parameter.value);
    if (!values) continue;
    const base = { name, unit: parameter.unit, description: parameter.description };
    const type = parameter.value_type;
    if ((type === "range" || type === "np.arange") && values.length === 3) {
      const [start, stop, step] = values as [number, number, number];
      if (step === 0 || (stop - start) / step <= 0) continue;
      const points = Math.ceil((stop - start) / step - 1e-9);
      sweeps.push({ ...base, spacing: "linear", start, stop: start + (points - 1) * step, points, step });
    } else if (type === "np.linspace" && values.length === 3) {
      const [start, stop, num] = values as [number, number, number];
      const points = Math.max(1, Math.round(num));
      sweeps.push({ ...base, spacing: "linear", start, stop, points, ...(points > 1 ? { step: (stop - start) / (points - 1) } : {}) });
    } else if (type === "np.logspace" && values.length === 3) {
      const [start, stop, num] = values as [number, number, number];
      sweeps.push({ ...base, spacing: "log", start: 10 ** start, stop: 10 ** stop, points: Math.max(1, Math.round(num)) });
    } else if (type === "list" || type === "" || values.length !== 3) {
      if (values.length < 2) continue;
      sweeps.push({ ...base, spacing: "list", start: Math.min(...values), stop: Math.max(...values), points: values.length });
    }
  }
  return sweeps;
}

/** A number for the model: up to four significant digits, no trailing zeros. */
export function formatNumber(value: number): string {
  if (!Number.isFinite(value)) return String(value);
  if (value === 0) return "0";
  // A log-spaced endpoint comes back as 499999.99999994; it is the integer it rounds to.
  const rounded = Math.round(value);
  if (rounded !== 0 && Math.abs(value - rounded) <= 1e-9 * Math.abs(value) && Math.abs(rounded) < 1e15) {
    return String(rounded);
  }
  const text = Math.abs(value) >= 1e6 || Math.abs(value) < 1e-4 ? value.toExponential(3) : value.toPrecision(4);
  return text.includes("e") ? text.replace(/\.?0+e/, "e") : text.replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
}

function withUnit(value: number, unit: string): string {
  const text = formatNumber(value);
  return unit && unit !== "a.u." ? `${text} ${unit}` : text;
}

/** One sweep as text, e.g. "time_range 0 to 400 ns in steps of 8 ns (51 points)". */
export function formatSweep(sweep: Sweep): string {
  const range = `${sweep.name} ${formatNumber(sweep.start)} to ${withUnit(sweep.stop, sweep.unit)}`;
  if (sweep.spacing === "log") return `${range}, ${sweep.points} points log-spaced`;
  if (sweep.spacing === "list") return `${range}, ${sweep.points} points`;
  return sweep.step === undefined ? `${range}, ${sweep.points} points` : `${range} in steps of ${withUnit(sweep.step, sweep.unit)} (${sweep.points} points)`;
}

/** Scalar settings as "name value unit" items, numbers and short strings only. */
export function formatSettings(parameters: Record<string, RecordedParameter>, skip: ReadonlySet<string> = new Set()): string[] {
  const items: string[] = [];
  for (const [name, parameter] of Object.entries(parameters)) {
    if (skip.has(name)) continue;
    const value = parameter.value;
    if (typeof value === "number") items.push(`${name} ${withUnit(value, parameter.unit)}`);
    else if (typeof value === "boolean") items.push(`${name} ${value}`);
    else if (typeof value === "string" && value.length <= 40) items.push(`${name} ${value}`);
  }
  return items;
}

export interface QcalContext {
  taskName?: string;
  status?: string;
  targetKind?: string;
  targetId?: string;
  chipId?: string;
  runParameters: Record<string, RecordedParameter>;
  /** Calibration inputs (previous values), shown only on request. */
  inputParameters?: Record<string, RecordedParameter>;
  /** Fitted results, shown only on request. */
  metrics?: Record<string, RecordedParameter>;
  message?: string;
}

/**
 * The context for `qcal_evaluate`: the task and target, then the sweep and
 * the other run settings. Inputs and fitted results are added only when the
 * caller asks, since the model is meant to read the plot.
 */
export function qcalContextText(context: QcalContext): string {
  let head = `Task ${context.taskName ?? "unknown"}`;
  if (context.targetId) {
    head += ` on ${context.targetKind && context.targetKind !== "system" ? `${context.targetKind} ${context.targetId}` : context.targetId}`;
  }
  if (context.chipId) head += ` (chip ${context.chipId})`;
  if (context.status) head += `, status ${context.status}`;
  const lines = [`${head}.`];
  const sweeps = sweepsOf(context.runParameters);
  if (sweeps.length > 0) lines.push(`Sweep: ${sweeps.map(formatSweep).join("; ")}.`);
  const settings = formatSettings(context.runParameters, new Set(sweeps.map((sweep) => sweep.name)));
  if (settings.length > 0) lines.push(`Settings: ${settings.join("; ")}.`);
  const inputs = context.inputParameters ? formatSettings(context.inputParameters) : [];
  if (inputs.length > 0) lines.push(`Calibration inputs: ${inputs.join("; ")}.`);
  const metrics = context.metrics ? formatSettings(context.metrics) : [];
  if (metrics.length > 0) lines.push(`Fitted results: ${metrics.join("; ")}.`);
  if (context.message?.trim()) lines.push(`Task message: ${context.message.trim()}`);
  return lines.join("\n");
}
