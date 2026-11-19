"use client";

import { type FormEvent, type ReactNode, useId, useMemo, useState } from "react";

import { useListCollisionChecks } from "@/client/collision-analysis/collision-analysis";
import type {
  DashboardPanelModel,
  DashboardPanelModelConfig,
  DashboardPanelModelType,
} from "@/schemas";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import { MarkdownEditor } from "@/components/ui/MarkdownEditor";
import { useMetricsConfig } from "@/hooks/useMetricsConfig";

import {
  ALL_HOPS,
  buildCollisionParams,
  collisionParamError,
  formatNumber,
  type MetricSelectionMode,
  PANEL_TYPES,
  readCollisionConfig,
  readMarkdownContent,
  readMetricConfig,
  SELECTION_MODES,
} from "./panelConfig";

/** What the editor returns; the page supplies the ID and layout. */
export interface PanelDraft {
  type: DashboardPanelModelType;
  title: string;
  config: DashboardPanelModelConfig;
}

function Field({
  id,
  label,
  hint,
  error,
  children,
}: {
  id: string;
  label: string;
  hint?: ReactNode;
  error?: string | null;
  children: ReactNode;
}) {
  return (
    <fieldset className="fieldset min-w-0">
      <legend className="fieldset-legend">
        <label htmlFor={id}>{label}</label>
      </legend>
      {children}
      {error ? (
        <p id={`${id}-error`} className="text-xs text-error">
          {error}
        </p>
      ) : hint ? (
        <p className="label whitespace-normal">{hint}</p>
      ) : null}
    </fieldset>
  );
}

interface PanelEditorFormProps {
  panel: DashboardPanelModel | null;
  onCancel: () => void;
  onSave: (draft: PanelDraft) => void;
}

function PanelEditorForm({ panel, onCancel, onSave }: PanelEditorFormProps) {
  const id = useId();
  const { qubitMetrics, couplingMetrics } = useMetricsConfig();
  const { data: catalogResponse, isLoading: isCatalogLoading } = useListCollisionChecks({
    query: { staleTime: Infinity },
  });
  const checks = useMemo(() => catalogResponse?.data.checks ?? [], [catalogResponse]);

  const initialType = panel?.type ?? "qubit_metric";
  const initialMetric = panel ? readMetricConfig(panel) : null;
  const initialCollision = panel ? readCollisionConfig(panel) : null;

  const [type, setType] = useState<DashboardPanelModelType>(initialType);
  const [title, setTitle] = useState(panel?.title ?? "");
  const [metric, setMetric] = useState(
    initialType === "qubit_metric" || initialType === "coupling_metric"
      ? (initialMetric?.metric ?? "")
      : "",
  );
  const [selectionMode, setSelectionMode] = useState<MetricSelectionMode>(
    initialMetric?.selection_mode ?? "latest",
  );
  const [check, setCheck] = useState(
    initialType === "collision_check" ? (initialCollision?.check ?? "") : "",
  );
  const [hops, setHops] = useState<number[]>(initialCollision?.hops ?? [...ALL_HOPS]);
  // Stored overrides of the panel being edited, then whatever the user types.
  const [baseParams, setBaseParams] = useState<Record<string, number>>(
    initialType === "collision_check" ? (initialCollision?.params ?? {}) : {},
  );
  const [paramInputs, setParamInputs] = useState<Record<string, string>>({});
  const [content, setContent] = useState(
    initialType === "markdown" && panel ? readMarkdownContent(panel) : "",
  );

  const metricOptions = type === "coupling_metric" ? couplingMetrics : qubitMetrics;
  const checkInfo = checks.find((entry) => entry.kind === check);
  const isPairCheck = checkInfo?.target === "pair";

  // Values that were typed or stored; untouched defaults are absent so that a
  // rounded display of the default is never saved as an override.
  const paramOverrides = useMemo(() => {
    const values: Record<string, string> = {};
    for (const parameter of checkInfo?.parameters ?? []) {
      const typed = paramInputs[parameter.name];
      const stored = baseParams[parameter.name];
      if (typed !== undefined) values[parameter.name] = typed;
      else if (stored !== undefined) values[parameter.name] = String(stored);
    }
    return values;
  }, [baseParams, checkInfo, paramInputs]);

  const paramValues = useMemo(() => {
    const values: Record<string, string> = {};
    for (const parameter of checkInfo?.parameters ?? []) {
      values[parameter.name] = paramOverrides[parameter.name] ?? formatNumber(parameter.default);
    }
    return values;
  }, [checkInfo, paramOverrides]);

  const paramErrors = useMemo(() => {
    const errors: Record<string, string> = {};
    for (const parameter of checkInfo?.parameters ?? []) {
      const message = collisionParamError(parameter, paramValues[parameter.name]);
      if (message) errors[parameter.name] = message;
    }
    return errors;
  }, [checkInfo, paramValues]);

  const missing: string | null = (() => {
    switch (type) {
      case "qubit_metric":
      case "coupling_metric":
        return metricOptions.some((entry) => entry.key === metric) ? null : "Choose a metric";
      case "collision_check":
        if (!checkInfo) return "Choose a collision check";
        if (isPairCheck && hops.length === 0) return "Choose at least one pair distance";
        if (Object.keys(paramErrors).length > 0) return "Fix the highlighted parameters";
        return null;
      case "markdown":
        return content.trim() ? null : "Write the note content";
    }
  })();

  const handleTypeChange = (next: DashboardPanelModelType) => {
    setType(next);
    if (next === "qubit_metric" || next === "coupling_metric") {
      const options = next === "coupling_metric" ? couplingMetrics : qubitMetrics;
      if (!options.some((entry) => entry.key === metric)) setMetric("");
    }
  };

  const handleCheckChange = (next: string) => {
    setCheck(next);
    setBaseParams({});
    setParamInputs({});
  };

  const toggleHop = (hop: number, checked: boolean) => {
    setHops((current) =>
      ALL_HOPS.filter((value) => (value === hop ? checked : current.includes(value))),
    );
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (missing) return;
    // Keep keys this editor does not manage, e.g. ones added by a newer client.
    const previous = panel && panel.type === type ? (panel.config ?? {}) : {};
    let config: DashboardPanelModelConfig;
    switch (type) {
      case "qubit_metric":
      case "coupling_metric":
        config = { ...previous, metric, selection_mode: selectionMode };
        break;
      case "collision_check":
        config = {
          ...previous,
          check,
          params: buildCollisionParams(checkInfo, paramOverrides),
          hops: isPairCheck ? hops : [...ALL_HOPS],
        };
        break;
      case "markdown":
        config = { ...previous, content };
        break;
    }
    onSave({ type, title: title.trim(), config });
  };

  return (
    <form className="flex flex-col gap-3" onSubmit={handleSubmit} noValidate>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field id={`${id}-type`} label="Panel type">
          <select
            id={`${id}-type`}
            className="select w-full"
            value={type}
            onChange={(event) => handleTypeChange(event.target.value as DashboardPanelModelType)}
          >
            {PANEL_TYPES.map((entry) => (
              <option key={entry.value} value={entry.value}>
                {entry.label}
              </option>
            ))}
          </select>
        </Field>
        <Field id={`${id}-title`} label="Title" hint="Leave empty to use the panel type">
          <input
            id={`${id}-title`}
            className="input w-full"
            value={title}
            maxLength={200}
            placeholder="Panel title"
            onChange={(event) => setTitle(event.target.value)}
          />
        </Field>
      </div>

      {(type === "qubit_metric" || type === "coupling_metric") && (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field id={`${id}-metric`} label="Metric">
            <select
              id={`${id}-metric`}
              className="select w-full"
              value={metric}
              onChange={(event) => setMetric(event.target.value)}
            >
              <option value="" disabled>
                Select a metric
              </option>
              {metricOptions.map((entry) => (
                <option key={entry.key} value={entry.key}>
                  {entry.title}
                  {entry.unit ? ` (${entry.unit})` : ""}
                </option>
              ))}
            </select>
          </Field>
          <Field id={`${id}-mode`} label="Value selection">
            <select
              id={`${id}-mode`}
              className="select w-full"
              value={selectionMode}
              onChange={(event) => setSelectionMode(event.target.value as MetricSelectionMode)}
            >
              {SELECTION_MODES.map((entry) => (
                <option key={entry.value} value={entry.value}>
                  {entry.label}
                </option>
              ))}
            </select>
          </Field>
        </div>
      )}

      {type === "collision_check" && (
        <>
          <Field
            id={`${id}-check`}
            label="Collision check"
            hint={checkInfo?.description ?? (isCatalogLoading ? "Loading checks" : undefined)}
          >
            <select
              id={`${id}-check`}
              className="select w-full"
              value={check}
              disabled={isCatalogLoading}
              onChange={(event) => handleCheckChange(event.target.value)}
            >
              <option value="" disabled>
                Select a check
              </option>
              {checks.map((entry) => (
                <option key={entry.kind} value={entry.kind}>
                  {entry.title}
                </option>
              ))}
            </select>
          </Field>

          {isPairCheck && (
            <fieldset className="fieldset">
              <legend className="fieldset-legend">Pair distance</legend>
              <div className="flex flex-wrap gap-4">
                {ALL_HOPS.map((hop) => (
                  <label key={hop} className="choice-field gap-2">
                    <input
                      type="checkbox"
                      className="checkbox checkbox-sm"
                      checked={hops.includes(hop)}
                      onChange={(event) => toggleHop(hop, event.target.checked)}
                    />
                    <span>{hop === 1 ? "1 hop (coupled pairs)" : "2 hops (next-nearest)"}</span>
                  </label>
                ))}
              </div>
            </fieldset>
          )}

          {checkInfo && checkInfo.parameters.length > 0 && (
            <fieldset className="fieldset rounded-[var(--radius-box)] border border-base-content/10 p-3">
              <legend className="fieldset-legend px-1">Parameters</legend>
              <p className="label whitespace-normal">
                Only values that differ from the default are saved with the panel
              </p>
              <div className="grid grid-cols-1 gap-x-3 gap-y-1 sm:grid-cols-2">
                {checkInfo.parameters.map((parameter) => {
                  const inputId = `${id}-param-${parameter.name}`;
                  const error = paramErrors[parameter.name];
                  const hintParts = [`Default ${formatNumber(parameter.default)}`];
                  if (parameter.min !== null && parameter.min !== undefined) {
                    hintParts.push(`min ${formatNumber(parameter.min)}`);
                  }
                  return (
                    <Field
                      key={parameter.name}
                      id={inputId}
                      label={`${parameter.label.replace(/_/g, " ")}${parameter.unit ? ` (${parameter.unit})` : ""}`}
                      hint={hintParts.join(" · ")}
                      error={error}
                    >
                      <input
                        id={inputId}
                        type="number"
                        step="any"
                        inputMode="decimal"
                        className={`input input-sm w-full ${error ? "input-error" : ""}`}
                        value={paramValues[parameter.name] ?? ""}
                        min={parameter.min ?? undefined}
                        aria-invalid={Boolean(error)}
                        aria-describedby={error ? `${inputId}-error` : undefined}
                        onChange={(event) =>
                          setParamInputs((current) => ({
                            ...current,
                            [parameter.name]: event.target.value,
                          }))
                        }
                      />
                    </Field>
                  );
                })}
              </div>
            </fieldset>
          )}
        </>
      )}

      {type === "markdown" && (
        <fieldset className="fieldset">
          <legend className="fieldset-legend">Content</legend>
          <MarkdownEditor
            value={content}
            onChange={setContent}
            rows={8}
            placeholder="Write Markdown"
          />
        </fieldset>
      )}

      <div className="modal-action mt-2 items-center">
        {missing && <p className="mr-auto text-xs text-base-content/60">{missing}</p>}
        <button type="button" className="btn btn-ghost" onClick={onCancel}>
          Cancel
        </button>
        <button type="submit" className="btn btn-primary" disabled={missing !== null}>
          {panel ? "Apply" : "Add panel"}
        </button>
      </div>
    </form>
  );
}

interface PanelEditorDialogProps {
  open: boolean;
  /** Panel being edited, or null to add a new one. */
  panel: DashboardPanelModel | null;
  onOpenChange: (open: boolean) => void;
  onSave: (draft: PanelDraft) => void;
}

/** Add or edit one dashboard panel. Changes stay local until the dashboard is saved. */
export function PanelEditorDialog({ open, panel, onOpenChange, onSave }: PanelEditorDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogTitle>{panel ? "Edit panel" : "Add panel"}</DialogTitle>
        <DialogDescription className="mt-1 text-xs text-base-content/60">
          Changes apply to the draft; save the dashboard to share them
        </DialogDescription>
        <div className="mt-3">
          <PanelEditorForm panel={panel} onCancel={() => onOpenChange(false)} onSave={onSave} />
        </div>
      </DialogContent>
    </Dialog>
  );
}
