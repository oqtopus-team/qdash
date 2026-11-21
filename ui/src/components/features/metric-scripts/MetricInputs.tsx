"use client";

import type { MetricInfo } from "@/schemas";

import {
  type ParamInputs,
  paramInputError,
  paramInputValue,
  parameterEntries,
  parameterLabel,
} from "./parameters";
import {
  absoluteFromDays,
  DEFAULT_PERIOD_DAYS,
  isoToLocalInput,
  localInputToIso,
  MAX_PERIOD_DAYS,
  type MetricPeriod,
  periodError,
} from "./periods";
import { formatNumber } from "./format";

interface PeriodFieldsProps {
  id: string;
  value: MetricPeriod;
  onChange: (period: MetricPeriod) => void;
  disabled?: boolean;
}

/**
 * Period editor: the last N days, or a fixed start and end in the UI time zone. The kind
 * and its values share one row at the small control size.
 */
export function PeriodFields({ id, value, onChange, disabled = false }: PeriodFieldsProps) {
  const error = periodError(value);
  const isAbsolute = value.kind === "absolute";
  const errorId = `${id}-error`;

  const handleKindChange = (kind: string) => {
    if (kind === "absolute" && !isAbsolute) {
      onChange(
        absoluteFromDays(
          value.kind === "relative" && Number.isFinite(value.days)
            ? value.days
            : DEFAULT_PERIOD_DAYS,
        ),
      );
    } else if (kind === "relative" && isAbsolute) {
      onChange({ kind: "relative", days: DEFAULT_PERIOD_DAYS });
    }
  };

  return (
    <fieldset className="min-w-0" disabled={disabled}>
      <div
        className={`grid grid-cols-1 gap-x-3 ${isAbsolute ? "sm:grid-cols-3" : "sm:grid-cols-2"}`}
      >
        <div className="fieldset min-w-0">
          <label htmlFor={`${id}-kind`} className="fieldset-legend">
            Period
          </label>
          <select
            id={`${id}-kind`}
            className="select select-sm w-full"
            value={value.kind}
            onChange={(event) => handleKindChange(event.target.value)}
          >
            <option value="relative">Last days</option>
            <option value="absolute">Fixed range</option>
          </select>
        </div>
        {value.kind === "absolute" ? (
          <>
            <div className="fieldset min-w-0">
              <label htmlFor={`${id}-start`} className="fieldset-legend">
                Start
              </label>
              <input
                id={`${id}-start`}
                type="datetime-local"
                className="input input-sm w-full"
                value={isoToLocalInput(value.start)}
                aria-invalid={Boolean(error)}
                aria-describedby={error ? errorId : undefined}
                onChange={(event) =>
                  onChange({ ...value, start: localInputToIso(event.target.value) })
                }
              />
            </div>
            <div className="fieldset min-w-0">
              <label htmlFor={`${id}-end`} className="fieldset-legend">
                End
              </label>
              <input
                id={`${id}-end`}
                type="datetime-local"
                className="input input-sm w-full"
                value={isoToLocalInput(value.end)}
                aria-invalid={Boolean(error)}
                aria-describedby={error ? errorId : undefined}
                onChange={(event) =>
                  onChange({ ...value, end: localInputToIso(event.target.value) })
                }
              />
            </div>
          </>
        ) : (
          <div className="fieldset min-w-0">
            <label htmlFor={`${id}-days`} className="fieldset-legend">
              Days back from now
            </label>
            <input
              id={`${id}-days`}
              type="number"
              inputMode="numeric"
              min={1}
              max={MAX_PERIOD_DAYS}
              step={1}
              className={`input input-sm w-full ${error ? "input-error" : ""}`}
              value={Number.isFinite(value.days) ? value.days : ""}
              aria-invalid={Boolean(error)}
              aria-describedby={error ? errorId : undefined}
              onChange={(event) => onChange({ kind: "relative", days: event.target.valueAsNumber })}
            />
          </div>
        )}
      </div>
      {error && (
        <p id={errorId} className="text-xs text-error">
          {error}
        </p>
      )}
    </fieldset>
  );
}

interface ParameterFieldsProps {
  id: string;
  metric: MetricInfo | undefined;
  inputs: ParamInputs;
  onChange: (inputs: ParamInputs) => void;
  disabled?: boolean;
}

/** One input per `Parameter` of a metric, generated from its kind and constraints. */
export function ParameterFields({
  id,
  metric,
  inputs,
  onChange,
  disabled = false,
}: ParameterFieldsProps) {
  const entries = parameterEntries(metric);
  if (entries.length === 0) return null;
  const set = (name: string, value: string | boolean) => onChange({ ...inputs, [name]: value });
  return (
    <fieldset className="fieldset min-w-0" disabled={disabled}>
      <legend className="fieldset-legend">Parameters</legend>
      <div className="grid grid-cols-1 gap-x-3 gap-y-2 sm:grid-cols-2">
        {entries.map(([name, info]) => {
          const inputId = `${id}-param-${name}`;
          const value = paramInputValue(name, info, inputs);
          const error = paramInputError(info, value);
          const label = parameterLabel(name, info);
          const hint = [
            `Default ${typeof info.default === "number" ? formatNumber(info.default) : String(info.default)}`,
            info.min != null ? `min ${formatNumber(info.min)}` : null,
            info.max != null ? `max ${formatNumber(info.max)}` : null,
          ]
            .filter(Boolean)
            .join(" · ");
          if (info.kind === "boolean") {
            return (
              <label key={name} htmlFor={inputId} className="choice-field gap-2 py-1">
                <input
                  id={inputId}
                  type="checkbox"
                  className="toggle toggle-sm"
                  checked={Boolean(value)}
                  onChange={(event) => set(name, event.target.checked)}
                />
                <span className="text-sm">{label}</span>
              </label>
            );
          }
          return (
            <div key={name} className="flex min-w-0 flex-col gap-1">
              <label htmlFor={inputId} className="label text-xs">
                {label}
              </label>
              {info.kind === "choice" ? (
                <select
                  id={inputId}
                  className="select select-sm w-full"
                  value={String(value)}
                  onChange={(event) => set(name, event.target.value)}
                >
                  {(info.choices ?? []).map((choice) => (
                    <option key={choice} value={choice}>
                      {choice}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  id={inputId}
                  type="number"
                  inputMode={info.kind === "integer" ? "numeric" : "decimal"}
                  step={info.step ?? (info.kind === "integer" ? 1 : "any")}
                  min={info.min ?? undefined}
                  max={info.max ?? undefined}
                  className={`input input-sm w-full ${error ? "input-error" : ""}`}
                  value={String(value)}
                  aria-invalid={Boolean(error)}
                  aria-describedby={`${inputId}-hint`}
                  onChange={(event) => set(name, event.target.value)}
                />
              )}
              <p
                id={`${inputId}-hint`}
                className={`text-xs ${error ? "text-error" : "text-base-content/60"}`}
              >
                {error ?? hint}
              </p>
            </div>
          );
        })}
      </div>
      <p className="label whitespace-normal">Only values that differ from the default are kept</p>
    </fieldset>
  );
}
