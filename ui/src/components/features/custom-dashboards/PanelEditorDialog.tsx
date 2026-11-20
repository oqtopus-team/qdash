"use client";

import { type FormEvent, type ReactNode, useId, useMemo, useState } from "react";

import { useGetMetricScript, useListMetricScripts } from "@/client/metric-script/metric-script";
import type {
  DashboardPanelModelConfig,
  DashboardPanelModelType,
  DashboardPanelResponse,
  MetricInfo,
} from "@/schemas";
import { displayUnit } from "@/components/features/metric-scripts/format";
import { declaredHops } from "@/components/features/metric-scripts/hops";
import { ParameterFields, PeriodFields } from "@/components/features/metric-scripts/MetricInputs";
import {
  type ParamInputs,
  paramInputsFrom,
  paramsFromInputs,
} from "@/components/features/metric-scripts/parameters";
import { periodError, type MetricPeriod } from "@/components/features/metric-scripts/periods";
import type { ResultViewMode } from "@/components/features/metric-scripts/render/MetricResultView";
import {
  PAIR_DIRECTIONS,
  type PairDirection,
} from "@/components/features/metric-scripts/render/PairMap";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import { MarkdownEditor } from "@/components/ui/MarkdownEditor";
import { useMetricsConfig } from "@/hooks/useMetricsConfig";

import {
  type MetricSelectionMode,
  PANEL_TYPES,
  readMarkdownContent,
  readMetricConfig,
  readMetricScriptConfig,
  SELECTION_MODES,
  writeMetricScriptConfig,
} from "./panelConfig";

/**
 * What the editor returns; the page supplies the ID and layout. A `metric_script` panel also
 * carries the script's name and active revision, as the API annotates saved panels.
 */
export interface PanelDraft {
  type: DashboardPanelModelType;
  title: string;
  config: DashboardPanelModelConfig;
  script_name: string | null;
  latest_revision: number | null;
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
  panel: DashboardPanelResponse | null;
  dashboardShared: boolean;
  onCancel: () => void;
  onSave: (draft: PanelDraft) => void;
}

function metricOptionLabel(metric: MetricInfo): string {
  const unit = displayUnit(metric.unit);
  return `${metric.title}${unit ? ` (${unit})` : ""} · ${metric.target}`;
}

function PanelEditorForm({ panel, dashboardShared, onCancel, onSave }: PanelEditorFormProps) {
  const id = useId();
  const { qubitMetrics, couplingMetrics } = useMetricsConfig();

  const initialType = panel?.type ?? "qubit_metric";
  const initialMetric = panel ? readMetricConfig(panel) : null;
  const initialScript = panel?.type === "metric_script" ? readMetricScriptConfig(panel) : null;

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
  const [content, setContent] = useState(
    initialType === "markdown" && panel ? readMarkdownContent(panel) : "",
  );

  // metric_script settings
  const [scriptId, setScriptId] = useState(initialScript?.script_id ?? "");
  const [revision, setRevision] = useState<number | null>(initialScript?.script_revision ?? null);
  const [scriptMetricId, setScriptMetricId] = useState(initialScript?.metric_id ?? "");
  const [period, setPeriod] = useState<MetricPeriod>(
    initialScript?.period ?? { kind: "relative", days: 14 },
  );
  // Stored overrides of the panel being edited, then whatever the user types.
  const [storedParams, setStoredParams] = useState<Record<string, unknown>>(
    initialScript?.params ?? {},
  );
  const [typedParams, setTypedParams] = useState<ParamInputs>({});
  const [view, setView] = useState<ResultViewMode>(initialScript?.view ?? "map");
  const [direction, setDirection] = useState<PairDirection>(initialScript?.direction ?? "both");
  const [hops, setHops] = useState<number[]>(initialScript?.hops ?? [1, 2]);

  const isScriptType = type === "metric_script";
  const scriptsQuery = useListMetricScripts({ query: { enabled: isScriptType } });
  const scripts = useMemo(() => scriptsQuery.data?.data.scripts ?? [], [scriptsQuery.data]);
  const detailQuery = useGetMetricScript(scriptId, {
    query: { enabled: isScriptType && !!scriptId },
  });
  const detail = detailQuery.data?.data;
  const summary = scripts.find((entry) => entry.script_id === scriptId);
  const selectable = scripts.filter((entry) => entry.active_revision !== null);
  const activeRevision = summary?.active_revision ?? detail?.active_revision ?? null;

  // The catalog of the pinned revision: from the script's revision list when loaded, else the
  // active catalog when the pin is the active revision.
  const catalog = useMemo<MetricInfo[]>(() => {
    if (revision === null) return [];
    const pinned = detail?.revisions.find((entry) => entry.revision === revision)?.metrics;
    if (pinned && pinned.length > 0) return pinned;
    if (summary && revision === summary.active_revision) return summary.metrics;
    if (detail && revision === detail.active_revision) return detail.metrics;
    return pinned ?? [];
  }, [detail, revision, summary]);
  const scriptMetric = catalog.find((entry) => entry.id === scriptMetricId);
  const isPairMetric = scriptMetric?.target === "pair";
  const hopOptions = declaredHops(scriptMetric);
  const shownHops = hops.filter((hop) => hopOptions.includes(hop));

  const paramInputs = useMemo(
    () => ({ ...paramInputsFrom(scriptMetric, storedParams), ...typedParams }),
    [scriptMetric, storedParams, typedParams],
  );
  const { params, errors: paramErrors } = paramsFromInputs(scriptMetric, paramInputs);

  const metricOptions = type === "coupling_metric" ? couplingMetrics : qubitMetrics;
  const catalogLoading = scriptsQuery.isLoading || (!!scriptId && detailQuery.isLoading);

  const missing: string | null = (() => {
    switch (type) {
      case "qubit_metric":
      case "coupling_metric":
        return metricOptions.some((entry) => entry.key === metric) ? null : "Choose a metric";
      case "metric_script":
        if (!scriptId) return "Choose a script";
        if (revision === null) return "The script has no valid revision to pin";
        if (!scriptMetric)
          return catalogLoading ? "Loading the script's metrics" : "Choose a metric";
        if (Object.keys(paramErrors).length > 0) return "Fix the highlighted parameters";
        if (isPairMetric && shownHops.length === 0) return "Choose at least one pair distance";
        return periodError(period);
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

  const resetMetric = (next: MetricInfo | undefined) => {
    setScriptMetricId(next?.id ?? "");
    setStoredParams({});
    setTypedParams({});
    setHops(declaredHops(next));
  };

  const handleScriptChange = (nextId: string) => {
    const next = scripts.find((entry) => entry.script_id === nextId);
    setScriptId(nextId);
    setRevision(next?.active_revision ?? null);
    resetMetric(next?.metrics.length === 1 ? next.metrics[0] : undefined);
  };

  const pinActiveRevision = () => {
    if (activeRevision === null) return;
    setRevision(activeRevision);
    const metrics =
      detail?.revisions.find((entry) => entry.revision === activeRevision)?.metrics ??
      summary?.metrics ??
      [];
    if (!metrics.some((entry) => entry.id === scriptMetricId)) resetMetric(undefined);
  };

  const toggleHop = (hop: number, checked: boolean) => {
    setHops(hopOptions.filter((value) => (value === hop ? checked : shownHops.includes(value))));
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (missing) return;
    // Keep keys this editor does not manage, e.g. ones added by a newer client. Metric script
    // configs are strict on the API side, so they are written field by field.
    const previous = panel && panel.type === type ? (panel.config ?? {}) : {};
    let config: DashboardPanelModelConfig;
    let annotations: Pick<PanelDraft, "script_name" | "latest_revision"> = {
      script_name: null,
      latest_revision: null,
    };
    switch (type) {
      case "qubit_metric":
      case "coupling_metric":
        config = { ...previous, metric, selection_mode: selectionMode };
        break;
      case "metric_script":
        config = writeMetricScriptConfig({
          script_id: scriptId,
          metric_id: scriptMetricId,
          script_revision: revision,
          period,
          params,
          view,
          direction,
          hops: isPairMetric ? shownHops : hopOptions,
        });
        annotations = {
          script_name: summary?.name ?? detail?.name ?? panel?.script_name ?? null,
          latest_revision: activeRevision ?? panel?.latest_revision ?? null,
        };
        break;
      case "markdown":
        config = { ...previous, content };
        break;
    }
    onSave({ type, title: title.trim(), config, ...annotations });
  };

  const privateOnShared = dashboardShared && summary?.visibility === "private";

  return (
    <form className="flex flex-col gap-2" onSubmit={handleSubmit} noValidate>
      <div className="grid grid-cols-1 gap-x-3 sm:grid-cols-2">
        <Field id={`${id}-type`} label="Panel type">
          <select
            id={`${id}-type`}
            className="select select-sm w-full"
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
            className="input input-sm w-full"
            value={title}
            maxLength={200}
            placeholder="Panel title"
            onChange={(event) => setTitle(event.target.value)}
          />
        </Field>
      </div>

      {(type === "qubit_metric" || type === "coupling_metric") && (
        <div className="grid grid-cols-1 gap-x-3 sm:grid-cols-2">
          <Field id={`${id}-metric`} label="Metric">
            <select
              id={`${id}-metric`}
              className="select select-sm w-full"
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
              className="select select-sm w-full"
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

      {type === "metric_script" && (
        <>
          <div className="grid grid-cols-1 gap-x-3 sm:grid-cols-2">
            <Field
              id={`${id}-script`}
              label="Script"
              hint={
                revision !== null ? (
                  <span className="flex flex-wrap items-center gap-2">
                    Pinned to r{revision}
                    {activeRevision !== null && activeRevision > revision && (
                      <button
                        type="button"
                        className="link link-primary"
                        onClick={pinActiveRevision}
                      >
                        Use active r{activeRevision}
                      </button>
                    )}
                  </span>
                ) : scriptsQuery.isLoading ? (
                  "Loading scripts"
                ) : selectable.length === 0 ? (
                  "No script has a valid revision yet"
                ) : undefined
              }
            >
              <select
                id={`${id}-script`}
                className="select select-sm w-full"
                value={scriptId}
                disabled={scriptsQuery.isLoading}
                onChange={(event) => handleScriptChange(event.target.value)}
              >
                <option value="" disabled>
                  Select a script
                </option>
                {scriptId && !selectable.some((entry) => entry.script_id === scriptId) && (
                  <option value={scriptId}>
                    {panel?.script_name ?? detail?.name ?? scriptId} (unavailable)
                  </option>
                )}
                {selectable.map((entry) => (
                  <option key={entry.script_id} value={entry.script_id}>
                    {entry.name}
                    {entry.visibility === "private" ? " (private)" : ""}
                  </option>
                ))}
              </select>
            </Field>
            <Field id={`${id}-script-metric`} label="Metric">
              <select
                id={`${id}-script-metric`}
                className="select select-sm w-full"
                value={scriptMetric ? scriptMetricId : ""}
                disabled={catalog.length === 0}
                onChange={(event) =>
                  resetMetric(catalog.find((entry) => entry.id === event.target.value))
                }
              >
                <option value="" disabled>
                  Select a metric
                </option>
                {catalog.map((entry) => (
                  <option key={entry.id} value={entry.id}>
                    {metricOptionLabel(entry)}
                  </option>
                ))}
              </select>
            </Field>
          </div>

          {privateOnShared && (
            <div role="status" className="alert alert-warning alert-soft text-sm">
              This script is private. A dashboard shared with the project can only use shared
              scripts; share the script before saving the dashboard.
            </div>
          )}

          <PeriodFields id={`${id}-period`} value={period} onChange={setPeriod} />

          <ParameterFields
            id={id}
            metric={scriptMetric}
            inputs={paramInputs}
            onChange={(inputs) => {
              setStoredParams({});
              setTypedParams(inputs);
            }}
          />

          <div className="grid grid-cols-1 gap-x-3 sm:grid-cols-2">
            <Field id={`${id}-view`} label="View">
              <select
                id={`${id}-view`}
                className="select select-sm w-full"
                value={view}
                onChange={(event) => setView(event.target.value as ResultViewMode)}
              >
                <option value="map">Map</option>
                <option value="table">Table</option>
              </select>
            </Field>
            {isPairMetric && (
              <Field id={`${id}-direction`} label="Direction">
                <select
                  id={`${id}-direction`}
                  className="select select-sm w-full"
                  value={direction}
                  onChange={(event) => setDirection(event.target.value as PairDirection)}
                >
                  {PAIR_DIRECTIONS.map((entry) => (
                    <option key={entry.value} value={entry.value} title={entry.title}>
                      {entry.label}
                    </option>
                  ))}
                </select>
              </Field>
            )}
            {isPairMetric && hopOptions.length > 1 && (
              <fieldset className="fieldset min-w-0">
                <legend className="fieldset-legend">Pair distance</legend>
                <div className="flex flex-wrap gap-x-4 gap-y-1">
                  {hopOptions.map((hop) => (
                    <label key={hop} className="choice-field gap-2">
                      <input
                        type="checkbox"
                        className="checkbox checkbox-sm"
                        checked={shownHops.includes(hop)}
                        onChange={(event) => toggleHop(hop, event.target.checked)}
                      />
                      <span>{hop === 1 ? "1 hop (coupled pairs)" : "2 hops (next-nearest)"}</span>
                    </label>
                  ))}
                </div>
              </fieldset>
            )}
          </div>
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
  panel: DashboardPanelResponse | null;
  /** The dashboard is shared with the project, so its scripts must be shared too. */
  dashboardShared?: boolean;
  onOpenChange: (open: boolean) => void;
  onSave: (draft: PanelDraft) => void;
}

/** Add or edit one dashboard panel. Changes stay local until the dashboard is saved. */
export function PanelEditorDialog({
  open,
  panel,
  dashboardShared = false,
  onOpenChange,
  onSave,
}: PanelEditorDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogTitle>{panel ? "Edit panel" : "Add panel"}</DialogTitle>
        <DialogDescription className="mt-1 text-xs text-base-content/60">
          Changes apply to the draft; save the dashboard to share them
        </DialogDescription>
        <div className="mt-3">
          <PanelEditorForm
            panel={panel}
            dashboardShared={dashboardShared}
            onCancel={() => onOpenChange(false)}
            onSave={onSave}
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}
