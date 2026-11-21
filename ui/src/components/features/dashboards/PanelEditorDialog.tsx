"use client";

import { type FormEvent, type ReactNode, useId, useMemo, useRef, useState } from "react";

import Link from "next/link";

import { useGetMetricScript, useListMetricScripts } from "@/client/metric-script/metric-script";
import type {
  DashboardPanelModelConfig,
  DashboardPanelModelType,
  DashboardPanelResponse,
  MetricInfo,
} from "@/schemas";
import { declaredHops } from "@/components/features/metric-scripts/hops";
import { ParameterFields, PeriodFields } from "@/components/features/metric-scripts/MetricInputs";
import {
  type ParamInputs,
  paramInputsFrom,
  parameterEntries,
  paramsFromInputs,
} from "@/components/features/metric-scripts/parameters";
import { periodError, type MetricPeriod } from "@/components/features/metric-scripts/periods";
import type { ResultViewMode } from "@/components/features/metric-scripts/render/MetricResultView";
import {
  isSeriesMetric,
  MAX_SERIES_TARGETS,
  parseTargets,
  targetsText,
} from "@/components/features/metric-scripts/targets";
import {
  PAIR_DIRECTIONS,
  type PairDirection,
} from "@/components/features/metric-scripts/render/PairMap";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import { MarkdownEditor } from "@/components/ui/MarkdownEditor";
import { useMetricsConfig } from "@/hooks/useMetricsConfig";

import {
  findChoiceOption,
  type MetricChoice,
  metricChoiceGroups,
  parseChoiceValue,
} from "./metricChoices";
import {
  type MetricSelectionMode,
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

/** The two things a panel can be from the user's point of view; metric panels pick a source. */
type PanelKind = "metric" | "note";

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

function initialChoice(panel: DashboardPanelResponse | null): MetricChoice | null {
  if (!panel) return null;
  switch (panel.type) {
    case "qubit_metric":
    case "coupling_metric": {
      const metric = readMetricConfig(panel).metric;
      return metric ? { kind: panel.type, metric } : null;
    }
    case "metric_script": {
      const config = readMetricScriptConfig(panel);
      return config.script_id
        ? { kind: "metric_script", script_id: config.script_id, metric_id: config.metric_id }
        : null;
    }
    case "markdown":
      return null;
  }
}

function PanelEditorForm({ panel, dashboardShared, onCancel, onSave }: PanelEditorFormProps) {
  const id = useId();
  const { qubitMetrics, couplingMetrics } = useMetricsConfig();

  const initialScript = panel?.type === "metric_script" ? readMetricScriptConfig(panel) : null;

  const [kind, setKind] = useState<PanelKind>(panel?.type === "markdown" ? "note" : "metric");
  const [title, setTitle] = useState(panel?.title ?? "");
  // The title follows the chosen metric until the user types one; saved titles are kept.
  const titleEdited = useRef(!!panel?.title);
  const [choice, setChoice] = useState<MetricChoice | null>(() => initialChoice(panel));
  const [selectionMode, setSelectionMode] = useState<MetricSelectionMode>(
    panel && (panel.type === "qubit_metric" || panel.type === "coupling_metric")
      ? readMetricConfig(panel).selection_mode
      : "latest",
  );
  const [content, setContent] = useState(
    panel?.type === "markdown" ? readMarkdownContent(panel) : "",
  );

  // Settings of a script metric. The revision is the pin; it only moves on explicit request.
  const [revision, setRevision] = useState<number | null>(initialScript?.script_revision ?? null);
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
  // A series metric charts only the targets typed here; nothing defaults to the whole chip.
  const [targetsInput, setTargetsInput] = useState(targetsText(initialScript?.targets ?? []));
  // Parameters and the revision sit behind a disclosure; it opens when a panel already
  // deviates from the defaults so nothing stored is out of sight.
  const [advancedOpen, setAdvancedOpen] = useState(
    Object.keys(initialScript?.params ?? {}).length > 0,
  );

  const isMetric = kind === "metric";
  const scriptChoice = choice?.kind === "metric_script" ? choice : null;
  const scriptId = scriptChoice?.script_id ?? "";

  const scriptsQuery = useListMetricScripts({ query: { enabled: isMetric } });
  const scripts = useMemo(() => scriptsQuery.data?.data.scripts ?? [], [scriptsQuery.data]);
  const detailQuery = useGetMetricScript(scriptId, { query: { enabled: isMetric && !!scriptId } });
  const detail = detailQuery.data?.data;
  const summary = scripts.find((entry) => entry.script_id === scriptId);
  const activeRevision = summary?.active_revision ?? detail?.active_revision ?? null;
  const scriptName = summary?.name ?? detail?.name ?? panel?.script_name ?? null;
  const updateAvailable = revision !== null && activeRevision !== null && activeRevision > revision;

  // The catalog of the pinned revision: from the script's revision list when loaded, else the
  // active catalog when the pin is the active revision.
  const catalog = useMemo<MetricInfo[]>(() => {
    if (!scriptId || revision === null) return [];
    const pinned = detail?.revisions.find((entry) => entry.revision === revision)?.metrics;
    if (pinned && pinned.length > 0) return pinned;
    if (summary && revision === summary.active_revision) return summary.metrics;
    if (detail && revision === detail.active_revision) return detail.metrics;
    return pinned ?? [];
  }, [detail, revision, scriptId, summary]);

  const groups = useMemo(
    () =>
      metricChoiceGroups({
        qubitMetrics,
        couplingMetrics,
        scripts,
        // A pin behind the active revision lists what that revision defines; a script that is
        // no longer offered (deleted, unshared) still shows the panel's own metric.
        pinnedCatalog:
          scriptId && (revision !== activeRevision || !summary)
            ? {
                script_id: scriptId,
                metrics: catalog,
                label: summary ? undefined : `${scriptName ?? scriptId} (unavailable)`,
              }
            : null,
      }),
    [
      activeRevision,
      catalog,
      couplingMetrics,
      qubitMetrics,
      revision,
      scriptId,
      scriptName,
      scripts,
      summary,
    ],
  );
  const selectedOption = findChoiceOption(groups, choice);
  const selectedGroup = selectedOption
    ? groups.find((group) => group.options.includes(selectedOption))
    : undefined;

  const scriptMetric = scriptChoice
    ? catalog.find((entry) => entry.id === scriptChoice.metric_id)
    : undefined;
  const isPairMetric = scriptMetric?.target === "pair";
  const isSeries = isSeriesMetric(scriptMetric);
  // Only views that can show the metric's result are offered.
  const panelView: ResultViewMode = isSeries ? "timeseries" : view === "timeseries" ? "map" : view;
  const parsedTargets = isSeries ? parseTargets(targetsInput, scriptMetric?.target) : null;
  const hopOptions = declaredHops(scriptMetric);
  const shownHops = hops.filter((hop) => hopOptions.includes(hop));
  const hasParameters = parameterEntries(scriptMetric).length > 0;

  const paramInputs = useMemo(
    () => ({ ...paramInputsFrom(scriptMetric, storedParams), ...typedParams }),
    [scriptMetric, storedParams, typedParams],
  );
  const { params, errors: paramErrors } = paramsFromInputs(scriptMetric, paramInputs);
  const paramsInvalid = Object.keys(paramErrors).length > 0;

  const catalogLoading = scriptsQuery.isLoading || (!!scriptId && detailQuery.isLoading);
  const scriptGone = !!scriptId && !summary && !scriptsQuery.isLoading && !!detailQuery.isError;

  const missing: string | null = (() => {
    if (kind === "note") return content.trim() ? null : "Write the note content";
    if (!choice) return catalogLoading ? "Loading metrics" : "Choose a metric";
    if (choice.kind !== "metric_script") return selectedOption ? null : "Choose a metric";
    if (scriptGone) return "This script is no longer available; choose another metric";
    if (revision === null) return "The script has no valid revision to pin";
    if (!scriptMetric) return catalogLoading ? "Loading the script's metrics" : "Choose a metric";
    if (paramsInvalid) return "Fix the highlighted parameters";
    if (parsedTargets?.error) return parsedTargets.error;
    if (isPairMetric && !isSeries && shownHops.length === 0) {
      return "Choose at least one pair distance";
    }
    return periodError(period, { series: isSeries });
  })();

  const resetScriptMetric = (next: MetricInfo | undefined) => {
    setStoredParams({});
    setTypedParams({});
    setHops(declaredHops(next));
    setTargetsInput("");
  };

  const handleChoiceChange = (value: string) => {
    const next = parseChoiceValue(value);
    if (!next) return;
    let metricTitle: string | undefined;
    if (next.kind === "metric_script") {
      const script = scripts.find((entry) => entry.script_id === next.script_id);
      const sameScript = next.script_id === scriptId;
      const source = sameScript ? catalog : (script?.metrics ?? []);
      const metric = source.find((entry) => entry.id === next.metric_id);
      metricTitle = metric?.title;
      if (!sameScript) {
        setRevision(script?.active_revision ?? null);
        resetScriptMetric(metric);
      } else if (next.metric_id !== scriptChoice?.metric_id) {
        resetScriptMetric(metric);
      }
    } else {
      const options = next.kind === "coupling_metric" ? couplingMetrics : qubitMetrics;
      metricTitle = options.find((entry) => entry.key === next.metric)?.title;
    }
    if (!titleEdited.current && metricTitle) setTitle(metricTitle);
    setChoice(next);
  };

  const useUpdatedDefinition = () => {
    if (activeRevision === null || !scriptChoice) return;
    setRevision(activeRevision);
    const metrics =
      detail?.revisions.find((entry) => entry.revision === activeRevision)?.metrics ??
      summary?.metrics ??
      [];
    const kept = metrics.find((entry) => entry.id === scriptChoice.metric_id);
    if (!kept) {
      // The metric no longer exists in the updated definition; ask for a new choice.
      resetScriptMetric(undefined);
      setChoice({ kind: "metric_script", script_id: scriptChoice.script_id, metric_id: "" });
    }
  };

  const toggleHop = (hop: number, checked: boolean) => {
    setHops(hopOptions.filter((value) => (value === hop ? checked : shownHops.includes(value))));
  };

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (missing) return;
    if (kind === "metric" && !choice) return;
    const type: DashboardPanelModelType = kind === "note" || !choice ? "markdown" : choice.kind;
    // Keep keys this editor does not manage, e.g. ones added by a newer client. Metric script
    // configs are strict on the API side, so they are written field by field.
    const previous = panel && panel.type === type ? (panel.config ?? {}) : {};
    let config: DashboardPanelModelConfig;
    let annotations: Pick<PanelDraft, "script_name" | "latest_revision"> = {
      script_name: null,
      latest_revision: null,
    };
    if (type === "markdown" || !choice) {
      config = { ...previous, content };
    } else if (choice.kind === "metric_script") {
      config = writeMetricScriptConfig({
        script_id: choice.script_id,
        metric_id: choice.metric_id,
        script_revision: revision,
        period,
        params,
        view: panelView,
        targets: parsedTargets?.keys ?? [],
        direction,
        hops: isPairMetric && !isSeries ? shownHops : hopOptions,
      });
      annotations = {
        script_name: scriptName,
        latest_revision: activeRevision ?? panel?.latest_revision ?? null,
      };
    } else {
      config = { ...previous, metric: choice.metric, selection_mode: selectionMode };
    }
    onSave({ type, title: title.trim(), config, ...annotations });
  };

  const privateOnShared = dashboardShared && summary?.visibility === "private";
  const scriptHref = scriptId ? `/dashboards/scripts/${scriptId}` : null;

  return (
    <form className="mt-3 flex min-h-0 flex-1 flex-col" onSubmit={handleSubmit} noValidate>
      {/* Fields scroll; the actions below stay in view on short screens. */}
      <div
        className="-mx-1 flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto px-1 pb-1"
        data-testid="panel-editor-body"
      >
        <fieldset className="fieldset min-w-0">
          <legend className="fieldset-legend">Panel</legend>
          <div className="join" role="radiogroup" aria-label="Panel kind">
            <input
              type="radio"
              name={`${id}-kind`}
              className="join-item btn btn-sm"
              aria-label="Metric"
              checked={kind === "metric"}
              onChange={() => setKind("metric")}
            />
            <input
              type="radio"
              name={`${id}-kind`}
              className="join-item btn btn-sm"
              aria-label="Note"
              checked={kind === "note"}
              onChange={() => setKind("note")}
            />
          </div>
        </fieldset>

        {isMetric && (
          <>
            <Field
              id={`${id}-show`}
              label="Show"
              hint={
                scriptsQuery.isLoading
                  ? "Loading metrics"
                  : groups.some((group) => group.key.startsWith("script:"))
                    ? "Chip metrics come from the latest calibration; script metrics are computed from the period you choose"
                    : "Chip metrics come from the latest calibration; computed metrics appear here once a script is saved"
              }
            >
              <select
                id={`${id}-show`}
                className="select select-sm w-full pe-8"
                value={selectedOption?.value ?? ""}
                disabled={groups.length === 0}
                title={selectedOption?.label}
                aria-describedby={selectedOption ? `${id}-show-selected` : undefined}
                onChange={(event) => handleChoiceChange(event.target.value)}
              >
                <option value="" disabled>
                  Select a metric
                </option>
                {groups.map((group) => (
                  <optgroup key={group.key} label={group.label}>
                    {group.options.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </select>
              {selectedOption && (
                // A closed select clips long names on narrow screens; repeat the full choice.
                <p id={`${id}-show-selected`} className="text-xs break-words">
                  {selectedOption.label}
                  {selectedGroup && (
                    <span className="text-base-content/60"> · {selectedGroup.label}</span>
                  )}
                </p>
              )}
            </Field>

            <div
              className={`grid grid-cols-1 gap-x-3 ${choice ? "sm:grid-cols-[minmax(0,1fr)_12rem]" : ""}`}
            >
              <Field id={`${id}-title`} label="Title" hint="Shown above the panel">
                <input
                  id={`${id}-title`}
                  className="input input-sm w-full"
                  value={title}
                  maxLength={200}
                  placeholder="Panel title"
                  onChange={(event) => {
                    titleEdited.current = event.target.value !== "";
                    setTitle(event.target.value);
                  }}
                />
              </Field>
              {choice && choice.kind !== "metric_script" && (
                <Field
                  id={`${id}-mode`}
                  label="Value selection"
                  hint="Which measurement of each target to show"
                >
                  <select
                    id={`${id}-mode`}
                    className="select select-sm w-full"
                    value={selectionMode}
                    onChange={(event) =>
                      setSelectionMode(event.target.value as MetricSelectionMode)
                    }
                  >
                    {SELECTION_MODES.map((entry) => (
                      <option key={entry.value} value={entry.value}>
                        {entry.label}
                      </option>
                    ))}
                  </select>
                </Field>
              )}
              {scriptChoice && (
                <Field
                  id={`${id}-view`}
                  label="View"
                  hint={isSeries ? "A time series is drawn as a chart" : undefined}
                >
                  <select
                    id={`${id}-view`}
                    className="select select-sm w-full"
                    value={panelView}
                    disabled={isSeries}
                    onChange={(event) => setView(event.target.value as ResultViewMode)}
                  >
                    {isSeries ? (
                      <option value="timeseries">Chart</option>
                    ) : (
                      <>
                        <option value="map">Map</option>
                        <option value="table">Table</option>
                      </>
                    )}
                  </select>
                </Field>
              )}
            </div>

            {scriptChoice && (
              <>
                <PeriodFields
                  id={`${id}-period`}
                  value={period}
                  onChange={setPeriod}
                  series={isSeries}
                />

                {isSeries && (
                  <Field
                    id={`${id}-targets`}
                    label={isPairMetric ? "Directed pairs" : "Qubits"}
                    hint={`Up to ${MAX_SERIES_TARGETS}, separated by commas${
                      isPairMetric
                        ? ", such as 0>1, 1>0 (each direction is its own line)"
                        : ", such as 0, 5"
                    }. Only these are evaluated.`}
                    error={targetsInput.trim() ? parsedTargets?.error : null}
                  >
                    <input
                      id={`${id}-targets`}
                      className="input input-sm w-full font-mono"
                      value={targetsInput}
                      placeholder={isPairMetric ? "0>1, 1>0" : "0, 5"}
                      onChange={(event) => setTargetsInput(event.target.value)}
                    />
                  </Field>
                )}

                {isPairMetric && !isSeries && (
                  <div className="grid grid-cols-1 gap-x-3 sm:grid-cols-2">
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
                    {hopOptions.length > 1 && (
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
                              <span>
                                {hop === 1 ? "1 hop (coupled pairs)" : "2 hops (next-nearest)"}
                              </span>
                            </label>
                          ))}
                        </div>
                      </fieldset>
                    )}
                  </div>
                )}

                {privateOnShared && (
                  <div role="status" className="alert alert-warning alert-soft text-sm">
                    <span>
                      This metric comes from a private script. A dashboard shared with the project
                      can only show shared scripts; this panel cannot be saved until the script is
                      shared.{" "}
                      {summary?.can_edit && scriptHref ? (
                        <Link href={`${scriptHref}#metric-script-settings`} className="link">
                          Open the script&apos;s settings
                        </Link>
                      ) : (
                        <>
                          Ask {summary?.owner_username ?? "its owner"} to share it, or choose
                          another metric.
                        </>
                      )}
                    </span>
                  </div>
                )}

                {updateAvailable && (
                  <div role="status" className="alert alert-info alert-soft text-sm">
                    <span>
                      The script has an updated definition. This panel keeps using the one it was
                      saved with until you switch.
                    </span>
                    <button type="button" className="btn btn-sm" onClick={useUpdatedDefinition}>
                      Use updated definition
                    </button>
                  </div>
                )}

                <details
                  className="collapse collapse-arrow rounded-[var(--radius-field)] border border-base-300"
                  open={advancedOpen || paramsInvalid}
                  onToggle={(event) => setAdvancedOpen(event.currentTarget.open)}
                >
                  <summary className="collapse-title min-h-0 py-2 text-sm">
                    Advanced
                    <span className="ml-2 text-xs text-base-content/60">
                      {hasParameters ? "Parameters and script revision" : "Script revision"}
                    </span>
                  </summary>
                  <div className="collapse-content flex flex-col gap-2 pb-2">
                    <ParameterFields
                      id={id}
                      metric={scriptMetric}
                      inputs={paramInputs}
                      onChange={(inputs) => {
                        setStoredParams({});
                        setTypedParams(inputs);
                      }}
                    />
                    <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
                      <dt className="text-base-content/60">Script</dt>
                      <dd className="min-w-0">
                        {scriptHref ? (
                          <Link href={scriptHref} className="link link-hover">
                            {scriptName ?? scriptId}
                          </Link>
                        ) : (
                          (scriptName ?? scriptId)
                        )}
                        {summary?.visibility === "private" && " (private)"}
                      </dd>
                      <dt className="text-base-content/60">Revision</dt>
                      <dd className="min-w-0" data-testid="panel-revision">
                        {revision === null ? "none valid" : `pinned to r${revision}`}
                        {activeRevision !== null && activeRevision !== revision
                          ? ` · active r${activeRevision}`
                          : ""}
                      </dd>
                    </dl>
                    <p className="text-xs text-base-content/60">
                      Panels keep the revision they were saved with, so edits to the script never
                      change a saved dashboard unnoticed. Edit the Python source or write a custom
                      calculation under{" "}
                      <Link href="/dashboards?tab=scripts" className="link link-hover">
                        Scripts
                      </Link>
                      .
                    </p>
                  </div>
                </details>
              </>
            )}
          </>
        )}

        {kind === "note" && (
          <>
            <Field id={`${id}-title`} label="Title" hint="Shown above the note">
              <input
                id={`${id}-title`}
                className="input input-sm w-full"
                value={title}
                maxLength={200}
                placeholder="Panel title"
                onChange={(event) => {
                  titleEdited.current = event.target.value !== "";
                  setTitle(event.target.value);
                }}
              />
            </Field>
            <fieldset className="fieldset">
              <legend className="fieldset-legend">Content</legend>
              <MarkdownEditor
                value={content}
                onChange={setContent}
                rows={8}
                placeholder="Write Markdown"
              />
            </fieldset>
          </>
        )}
      </div>

      <div className="modal-action mt-3 shrink-0 items-center border-t border-base-300 pt-3">
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
      <DialogContent className="flex max-w-2xl flex-col overflow-hidden p-4 sm:p-6">
        <DialogTitle>{panel ? "Edit panel" : "Add panel"}</DialogTitle>
        <DialogDescription className="mt-1 text-xs text-base-content/60">
          Choose what to show and over which period; save the dashboard to keep the change
        </DialogDescription>
        <PanelEditorForm
          panel={panel}
          dashboardShared={dashboardShared}
          onCancel={() => onOpenChange(false)}
          onSave={onSave}
        />
      </DialogContent>
    </Dialog>
  );
}
