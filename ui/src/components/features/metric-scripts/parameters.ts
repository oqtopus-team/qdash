import type { MetricInfo, MetricParameterInfo } from "@/schemas";

import { displayUnit, formatNumber } from "./format";

/** A parameter value as the API stores it. */
export type ParamValue = boolean | number | string;

/**
 * What a parameter input holds: the typed text of a numeric or choice input, or the state of
 * a boolean switch. Untouched parameters are absent, so a rounded default is never stored.
 */
export type ParamInputs = Record<string, string | boolean>;

export function parameterEntries(
  metric: MetricInfo | undefined,
): Array<[string, MetricParameterInfo]> {
  return Object.entries(metric?.parameters ?? {});
}

/** Human label of a parameter, with its unit. */
export function parameterLabel(name: string, info: MetricParameterInfo): string {
  const label = (info.label || name).replace(/_/g, " ");
  const unit = displayUnit(info.unit);
  return unit ? `${label} (${unit})` : label;
}

/** Inputs that show the stored overrides of `metric`; unknown names are dropped. */
export function paramInputsFrom(
  metric: MetricInfo | undefined,
  stored: Record<string, unknown>,
): ParamInputs {
  const inputs: ParamInputs = {};
  for (const [name, info] of parameterEntries(metric)) {
    const value = stored[name];
    if (value === undefined) continue;
    if (info.kind === "boolean") {
      if (typeof value === "boolean") inputs[name] = value;
    } else if (typeof value === "number" || typeof value === "string") {
      inputs[name] = String(value);
    }
  }
  return inputs;
}

/** The value an input shows: what was typed or stored, else the default. */
export function paramInputValue(
  name: string,
  info: MetricParameterInfo,
  inputs: ParamInputs,
): string | boolean {
  const input = inputs[name];
  if (input !== undefined) return input;
  if (info.kind === "boolean") return Boolean(info.default);
  if (typeof info.default === "number") return formatNumber(info.default);
  return String(info.default);
}

/** Validation message of one input, or null when it is acceptable. */
export function paramInputError(info: MetricParameterInfo, input: string | boolean): string | null {
  if (info.kind === "boolean") return null;
  if (info.kind === "choice") {
    return info.choices?.includes(String(input)) ? null : "Choose one of the options";
  }
  const raw = String(input).trim();
  if (raw === "") return "Enter a value";
  const value = Number(raw);
  if (!Number.isFinite(value)) return "Enter a number";
  if (info.kind === "integer" && !Number.isInteger(value)) return "Enter a whole number";
  if (info.min !== null && info.min !== undefined && value < info.min) {
    return `Must be at least ${formatNumber(info.min)}`;
  }
  if (info.max !== null && info.max !== undefined && value > info.max) {
    return `Must be at most ${formatNumber(info.max)}`;
  }
  return null;
}

function sameValue(a: ParamValue, b: ParamValue): boolean {
  if (typeof a === "number" && typeof b === "number") {
    return Math.abs(a - b) <= 1e-12 * Math.max(1, Math.abs(b));
  }
  return a === b;
}

/**
 * The overrides worth storing for `metric` and the input errors. Only values that differ from
 * the default are kept; an input with an error is left out of `params`.
 */
export function paramsFromInputs(
  metric: MetricInfo | undefined,
  inputs: ParamInputs,
): { params: Record<string, ParamValue>; errors: Record<string, string> } {
  const params: Record<string, ParamValue> = {};
  const errors: Record<string, string> = {};
  for (const [name, info] of parameterEntries(metric)) {
    const input = inputs[name];
    if (input === undefined) continue;
    const error = paramInputError(info, input);
    if (error) {
      errors[name] = error;
      continue;
    }
    const value: ParamValue =
      info.kind === "boolean"
        ? Boolean(input)
        : info.kind === "choice"
          ? String(input)
          : Number(String(input).trim());
    if (!sameValue(value, info.default)) params[name] = value;
  }
  return { params, errors };
}

function formatParamValue(value: unknown, info: MetricParameterInfo | undefined): string {
  if (typeof value === "number") {
    const unit = displayUnit(info?.unit);
    return unit ? `${formatNumber(value)} ${unit}` : formatNumber(value);
  }
  if (typeof value === "boolean") return value ? "on" : "off";
  return String(value);
}

/** "Minimum observations 3 · window 10 MHz" from effective parameter values. */
export function formatParams(params: Record<string, unknown>, metric: MetricInfo | undefined) {
  return Object.entries(params)
    .map(([name, value]) => {
      const info = metric?.parameters?.[name];
      const label = (info?.label || name).replace(/_/g, " ");
      return `${label} ${formatParamValue(value, info)}`;
    })
    .join(" · ");
}
