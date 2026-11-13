const SWEEP_VALUE_TYPES = ["np.linspace", "np.logspace", "np.arange", "range"] as const;
export type SweepValueType = (typeof SWEEP_VALUE_TYPES)[number];
/** The forms a parameter declared with a sweep constructor can run in. */
export type SweepFormType = SweepValueType | "list";
export const SWEEP_FORM_TYPES: readonly SweepFormType[] = [...SWEEP_VALUE_TYPES, "list"];
const RANGE_VALUE_TYPES = new Set<string>(SWEEP_VALUE_TYPES);

/** Argument labels of each three-argument sweep constructor, in call order. */
export const SWEEP_ARGUMENT_NAMES: Record<SweepValueType, readonly [string, string, string]> = {
  "np.linspace": ["start", "stop", "num"],
  "np.logspace": ["start (10^)", "stop (10^)", "num"],
  "np.arange": ["start", "stop", "step"],
  range: ["start", "stop", "step"],
};

export function isSweepValueType(valueType: unknown): valueType is SweepValueType {
  return RANGE_VALUE_TYPES.has(String(valueType));
}

export function isSweepFormType(valueType: unknown): valueType is SweepFormType {
  return isSweepValueType(valueType) || valueType === "list";
}

/** Whether a value of `requested` type may set a parameter declared as `declared`. */
export function isCompatibleValueType(declared: unknown, requested: unknown): boolean {
  if (requested === null || requested === undefined || requested === declared) return true;
  if (isSweepValueType(declared)) return isSweepFormType(requested);
  return !isSweepFormType(requested);
}

const MAX_SWEEP_POINTS = 100_000;

/**
 * Materialize the points a sweep value produces, or null when the value cannot
 * be expanded (wrong shape, a zero step, a non-positive count, too many points).
 */
export function expandSweep(type: SweepFormType, value: unknown): number[] | null {
  if (!Array.isArray(value)) return null;
  const numbers = value.map((item) => (typeof item === "number" ? item : Number(item)));
  if (numbers.some((item) => !Number.isFinite(item))) return null;
  if (type === "list") return numbers;
  if (numbers.length !== 3) return null;
  const [start, stop, third] = numbers;
  if (type === "np.linspace" || type === "np.logspace") {
    if (!Number.isInteger(third) || third < 1 || third > MAX_SWEEP_POINTS) return null;
    const points = Array.from({ length: third }, (_, index) =>
      third === 1 ? start : start + ((stop - start) * index) / (third - 1),
    );
    return type === "np.logspace" ? points.map((exponent) => 10 ** exponent) : points;
  }
  if (type === "range" && !numbers.every(Number.isInteger)) return null;
  if (third === 0) return null;
  const count = Math.max(0, Math.ceil((stop - start) / third));
  if (count > MAX_SWEEP_POINTS) return null;
  return Array.from({ length: count }, (_, index) => start + index * third);
}

function roundArgument(argument: number): number {
  return Number(argument.toPrecision(12));
}

/**
 * The arguments that express a sweep in another form, or null when the sweep is blank or
 * the form cannot express it (a non-integer `range`, a non-positive `np.logspace` endpoint).
 * The linear forms (`np.linspace`, `np.arange`, `range`, a uniform `list`) keep the same points;
 * any other change keeps the first point, the last point, and the number of points.
 */
export function convertSweep(
  from: SweepFormType,
  value: unknown,
  to: SweepFormType,
): number[] | null {
  if (from === to) return null;
  const points = expandSweep(from, value);
  if (points === null || points.length === 0) return null;
  if (to === "list") return points;
  if (isArangeForm(from) && isArangeForm(to)) {
    // Both forms take start, stop, and step, so keep the arguments as typed.
    const args = (value as unknown[]).map(Number);
    return expandSweep(to, args) === null ? null : args;
  }
  const first = roundArgument(points[0]);
  const last = roundArgument(points[points.length - 1]);
  const count = points.length;
  if (to === "np.linspace") return [first, last, count];
  if (to === "np.logspace") {
    if (first <= 0 || last <= 0) return null;
    return [roundArgument(Math.log10(first)), roundArgument(Math.log10(last)), count];
  }
  // np.arange and range exclude the stop, so stop one step past the last point, or half a
  // step when floating-point rounding would let an extra point in.
  const step = count === 1 ? 1 : roundArgument((last - first) / (count - 1));
  if (step === 0) return null;
  const stop = [last + step, last + step / 2]
    .map(roundArgument)
    .find((candidate) => expandSweep("np.arange", [first, candidate, step])?.length === count);
  if (stop === undefined) return null;
  const args = [first, stop, step];
  return expandSweep(to, args) === null ? null : args;
}

function isArangeForm(type: SweepFormType): boolean {
  return type === "np.arange" || type === "range";
}

function formatPoint(point: number): string {
  return String(Number(point.toPrecision(6)));
}

/** A one-line summary of the points a sweep produces, such as `11 points: 0 to 100`. */
export function describeSweep(type: SweepFormType, value: unknown): string | null {
  const points = expandSweep(type, value);
  if (points === null) return null;
  if (points.length === 0) return "0 points";
  if (points.length === 1) return `1 point: ${formatPoint(points[0])}`;
  return `${points.length} points: ${formatPoint(points[0])} to ${formatPoint(points[points.length - 1])}`;
}

/** Show a recorded sweep as the call that produced it, such as `np.linspace(0, 1, 11)`. */
export function formatSweepValue(valueType: unknown, value: unknown): string | null {
  if (!Array.isArray(value) || !isSweepValueType(valueType) || value.length !== 3) return null;
  return `${valueType}(${value.join(", ")})`;
}

export interface TaskParameterUiGroup {
  name: string;
  collapsed: boolean;
}

export function getTaskParameterUiGroup(parameter: unknown): TaskParameterUiGroup | null {
  if (typeof parameter !== "object" || parameter === null) return null;
  const metadata = parameter as Record<string, unknown>;
  if (typeof metadata.ui_group !== "string" || metadata.ui_group.length === 0) return null;
  return {
    name: metadata.ui_group,
    collapsed: metadata.ui_group_collapsed === true,
  };
}

export function formatTaskParameter(value: unknown): string {
  if (value === null || value === undefined) return "";
  return Array.isArray(value) ? JSON.stringify(value) : String(value);
}

export function parseTaskParameter(raw: string, valueType: unknown): unknown {
  const normalized = raw.trim();
  if (valueType === "int") {
    const value = Number(normalized);
    if (!Number.isInteger(value)) throw new Error(`Expected an integer, got "${raw}"`);
    return value;
  }
  if (valueType === "float") {
    const value = Number(normalized);
    if (!Number.isFinite(value)) throw new Error(`Expected a finite number, got "${raw}"`);
    return value;
  }
  if (valueType === "list" || RANGE_VALUE_TYPES.has(String(valueType))) {
    const value: unknown = JSON.parse(normalized);
    if (!Array.isArray(value)) throw new Error(`Expected a JSON array, got "${raw}"`);
    if (valueType !== "list" && value.length !== 3) {
      throw new Error(`Expected exactly 3 array values for ${String(valueType)}`);
    }
    return value;
  }
  if (valueType === "bool") {
    if (normalized.toLowerCase() === "true") return true;
    if (normalized.toLowerCase() === "false") return false;
    throw new Error(`Expected true or false, got "${raw}"`);
  }
  if (valueType === "str" || valueType === "string") return raw;

  if (normalized === "true") return true;
  if (normalized === "false") return false;
  const numericValue = Number(normalized);
  return normalized !== "" && Number.isFinite(numericValue) ? numericValue : raw;
}
