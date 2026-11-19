"use client";

import type { MetricInfo } from "@/schemas";
import { ChipSelector } from "@/components/selectors/ChipSelector";

import { displayUnit } from "./format";
import { declaredHops } from "./hops";
import { ParameterFields, PeriodFields } from "./MetricInputs";
import type { ParamInputs } from "./parameters";
import type { MetricPeriod } from "./periods";
import { PAIR_DIRECTIONS, type PairDirection } from "./render/PairMap";
import type { ResultViewMode } from "./render/MetricResultView";

export interface PreviewSettings {
  chipId: string;
  metricId: string;
  period: MetricPeriod;
  paramInputs: ParamInputs;
  view: ResultViewMode;
  direction: PairDirection;
  hops: number[];
}

interface PreviewControlsProps {
  id: string;
  metrics: readonly MetricInfo[];
  value: PreviewSettings;
  onChange: (patch: Partial<PreviewSettings>) => void;
}

/** What a preview evaluates and how it is shown: chip, metric, period, parameters and view. */
export function PreviewControls({ id, metrics, value, onChange }: PreviewControlsProps) {
  const metric = metrics.find((entry) => entry.id === value.metricId);
  const isPair = metric?.target === "pair";
  const hopOptions = declaredHops(metric);

  return (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <fieldset className="fieldset min-w-0">
          <legend className="fieldset-legend">
            <label htmlFor={`${id}-chip`}>Chip</label>
          </legend>
          <ChipSelector
            inputId={`${id}-chip`}
            selectedChip={value.chipId}
            onChipSelect={(chipId) => onChange({ chipId })}
          />
        </fieldset>
        <fieldset className="fieldset min-w-0">
          <legend className="fieldset-legend">
            <label htmlFor={`${id}-metric`}>Metric</label>
          </legend>
          <select
            id={`${id}-metric`}
            className="select select-sm w-full"
            value={metric ? value.metricId : ""}
            disabled={metrics.length === 0}
            onChange={(event) => {
              const next = metrics.find((entry) => entry.id === event.target.value);
              onChange({ metricId: event.target.value, paramInputs: {}, hops: declaredHops(next) });
            }}
          >
            <option value="" disabled>
              {metrics.length === 0 ? "Validate the script to list its metrics" : "Select a metric"}
            </option>
            {metrics.map((entry) => {
              const unit = displayUnit(entry.unit);
              return (
                <option key={entry.id} value={entry.id}>
                  {entry.title}
                  {unit ? ` (${unit})` : ""} · {entry.target}
                </option>
              );
            })}
          </select>
        </fieldset>
      </div>

      <PeriodFields
        id={`${id}-period`}
        value={value.period}
        onChange={(period) => onChange({ period })}
      />

      <ParameterFields
        id={id}
        metric={metric}
        inputs={value.paramInputs}
        onChange={(paramInputs) => onChange({ paramInputs })}
      />

      <div className="flex flex-wrap items-end gap-x-4 gap-y-2">
        <fieldset className="fieldset">
          <legend className="fieldset-legend">View</legend>
          <div className="join" role="group" aria-label="View">
            {(["map", "table"] as const).map((view) => (
              <button
                key={view}
                type="button"
                aria-pressed={value.view === view}
                className={`btn btn-xs join-item ${value.view === view ? "btn-active" : ""}`}
                onClick={() => onChange({ view })}
              >
                {view === "map" ? "Map" : "Table"}
              </button>
            ))}
          </div>
        </fieldset>
        {isPair && (
          <>
            <fieldset className="fieldset">
              <legend className="fieldset-legend">Direction</legend>
              <div className="join" role="group" aria-label="Direction">
                {PAIR_DIRECTIONS.map((entry) => (
                  <button
                    key={entry.value}
                    type="button"
                    title={entry.title}
                    aria-pressed={value.direction === entry.value}
                    className={`btn btn-xs join-item ${value.direction === entry.value ? "btn-active" : ""}`}
                    onClick={() => onChange({ direction: entry.value })}
                  >
                    {entry.label}
                  </button>
                ))}
              </div>
            </fieldset>
            {hopOptions.length > 1 && (
              <fieldset className="fieldset">
                <legend className="fieldset-legend">Pair distance</legend>
                <div className="flex flex-wrap gap-3">
                  {hopOptions.map((hop) => (
                    <label key={hop} className="choice-field gap-1.5 text-sm">
                      <input
                        type="checkbox"
                        className="checkbox checkbox-xs"
                        checked={value.hops.includes(hop)}
                        onChange={(event) =>
                          onChange({
                            hops: hopOptions.filter((entry) =>
                              entry === hop ? event.target.checked : value.hops.includes(entry),
                            ),
                          })
                        }
                      />
                      {hop === 1 ? "1 hop" : "2 hops"}
                    </label>
                  ))}
                </div>
              </fieldset>
            )}
          </>
        )}
      </div>
    </div>
  );
}
