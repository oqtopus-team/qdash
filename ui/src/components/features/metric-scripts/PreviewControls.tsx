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

/**
 * What a preview evaluates and how it is shown: chip, metric, period, parameters and view.
 * The same controls as the panel editor, so a script previews the way its panel will look.
 */
export function PreviewControls({ id, metrics, value, onChange }: PreviewControlsProps) {
  const metric = metrics.find((entry) => entry.id === value.metricId);
  const isPair = metric?.target === "pair";
  const hopOptions = declaredHops(metric);

  return (
    <div className="flex flex-col gap-2">
      <div className="grid grid-cols-1 gap-x-3 sm:grid-cols-2">
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

      <div className="grid grid-cols-1 gap-x-3 sm:grid-cols-2">
        <fieldset className="fieldset min-w-0">
          <legend className="fieldset-legend">
            <label htmlFor={`${id}-view`}>View</label>
          </legend>
          <select
            id={`${id}-view`}
            className="select select-sm w-full"
            value={value.view}
            onChange={(event) => onChange({ view: event.target.value as ResultViewMode })}
          >
            <option value="map">Map</option>
            <option value="table">Table</option>
          </select>
        </fieldset>
        {isPair && (
          <fieldset className="fieldset min-w-0">
            <legend className="fieldset-legend">
              <label htmlFor={`${id}-direction`}>Direction</label>
            </legend>
            <select
              id={`${id}-direction`}
              className="select select-sm w-full"
              value={value.direction}
              onChange={(event) => onChange({ direction: event.target.value as PairDirection })}
            >
              {PAIR_DIRECTIONS.map((entry) => (
                <option key={entry.value} value={entry.value} title={entry.title}>
                  {entry.label}
                </option>
              ))}
            </select>
          </fieldset>
        )}
        {isPair && hopOptions.length > 1 && (
          <fieldset className="fieldset min-w-0">
            <legend className="fieldset-legend">Pair distance</legend>
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              {hopOptions.map((hop) => (
                <label key={hop} className="choice-field gap-2">
                  <input
                    type="checkbox"
                    className="checkbox checkbox-sm"
                    checked={value.hops.includes(hop)}
                    onChange={(event) =>
                      onChange({
                        hops: hopOptions.filter((entry) =>
                          entry === hop ? event.target.checked : value.hops.includes(entry),
                        ),
                      })
                    }
                  />
                  <span>{hop === 1 ? "1 hop (coupled pairs)" : "2 hops (next-nearest)"}</span>
                </label>
              ))}
            </div>
          </fieldset>
        )}
      </div>
    </div>
  );
}
