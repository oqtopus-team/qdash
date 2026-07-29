"use client";

import React, { useEffect, useMemo, useRef, useState } from "react";

import type { PlotMouseEvent } from "plotly.js";

import dynamic from "next/dynamic";
import { RotateCcw } from "lucide-react";

import {
  CommitParametersModal,
  type CommitParameterRow,
} from "@/components/features/parameters/CommitParametersModal";
import {
  formatOutputValue,
  OutputParameterTable,
  parseFloatOrNull,
  type OutputParameterEditRow,
} from "@/components/features/parameters/OutputParameterTable";

import type {
  ReanalyzeQubitSpectroscopyParams,
  ReanalyzeResonatorSpectroscopyParams,
} from "@/schemas";

import {
  useCommitReanalyzeResonatorSpectroscopy,
  useReanalyzeQubitSpectroscopy,
  useReanalyzeResonatorSpectroscopy,
} from "@/client/chip/chip";

// Plotly references `window` at import time, so we can't SSR it. Load lazily on the client.
const Plot = dynamic(() => import("@/components/charts/Plot"), { ssr: false });

type ReanalyzeKind = "resonator" | "qubit";

interface ReanalysisPanelProps {
  chipId: string;
  qubitId: string;
  /** Workflow task name, used to pick which analysis pipeline to call. */
  taskName: string;
  /** Specific task result to re-analyze. Falls back to "latest" on the server when null. */
  sourceTaskId?: string | null;
  /** Point picked on an external Plotly figure, such as TaskDetailModal interactive view. */
  pickedPoint?: PickedPoint | null;
}

const RESONATOR_TASK = "CheckResonatorSpectroscopy";
const QUBIT_TASK = "CheckQubitSpectroscopy";

/** A point read off the spectroscopy map: frequency on x, readout power on y. */
export interface PickedPoint {
  x: number;
  y: number;
  token: number;
}

export function ReanalysisPanel({
  chipId,
  qubitId,
  taskName,
  sourceTaskId,
  pickedPoint,
}: ReanalysisPanelProps) {
  const kind: ReanalyzeKind | null =
    taskName === RESONATOR_TASK ? "resonator" : taskName === QUBIT_TASK ? "qubit" : null;

  if (!kind) return null;

  return kind === "resonator" ? (
    <ResonatorReanalysis
      chipId={chipId}
      qubitId={qubitId}
      sourceTaskId={sourceTaskId}
      pickedPoint={pickedPoint}
    />
  ) : (
    <QubitReanalysis chipId={chipId} qubitId={qubitId} sourceTaskId={sourceTaskId} />
  );
}

// ── Resonator-spectroscopy panel ──────────────────────────────────────────

/** User-typed values, keyed by qid and parameter name. Everything else follows the analysis. */
type OutputOverrideForm = Record<string, Record<string, string>>;

/** Parameters a click on the spectroscopy map fills, in axis order. */
const PICKED_FROM_PLOT = { x: "readout_frequency", y: "optimal_power" } as const;

function ResonatorReanalysis({
  chipId,
  qubitId,
  sourceTaskId,
  pickedPoint,
}: Omit<ReanalysisPanelProps, "taskName">) {
  const [outputOverrides, setOutputOverrides] = useState<OutputOverrideForm>({});
  /** qid armed to receive the next point picked from the plot. */
  const [pickTargetQid, setPickTargetQid] = useState<string | null>(null);
  const [isCommitConfirmOpen, setIsCommitConfirmOpen] = useState(false);
  const didAutoPreviewRef = useRef(false);
  const mutation = useReanalyzeResonatorSpectroscopy();
  const commitMutation = useCommitReanalyzeResonatorSpectroscopy();

  // Only an armed qubit takes a picked point, so a stray plot click cannot overwrite typed input.
  // One click fixes both axes, and the preview is redrawn right away.
  const applyPickedPoint = (x: number, y: number) => {
    if (!pickTargetQid) return;
    const nextOverrides: OutputOverrideForm = {
      ...outputOverrides,
      [pickTargetQid]: {
        ...(outputOverrides[pickTargetQid] ?? {}),
        [PICKED_FROM_PLOT.x]: x.toFixed(6),
        [PICKED_FROM_PLOT.y]: y.toFixed(6),
      },
    };
    setOutputOverrides(nextOverrides);
    setPickTargetQid(null);
    commitMutation.reset();
    mutation.mutate(buildRequestWith(nextOverrides));
  };

  useEffect(() => {
    if (!pickedPoint || !Number.isFinite(pickedPoint.x) || !Number.isFinite(pickedPoint.y)) return;
    applyPickedPoint(pickedPoint.x, pickedPoint.y);
    // pickedPoint.token intentionally lets repeated clicks on the same point apply again.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pickedPoint?.token]);

  // Takes the overrides explicitly so a freshly picked value can be sent before state settles.
  const buildRequestWith = (overrides: OutputOverrideForm) => {
    // Everything the analysis decides is left to the server; only per-qubit edits are sent.
    const params: ReanalyzeResonatorSpectroscopyParams = {
      output_parameter_overrides: numericOverrides(overrides),
    };
    return {
      chipId,
      qid: qubitId,
      data: {
        source_task_id: sourceTaskId ?? null,
        parameters: params,
      },
    };
  };

  const buildRequest = () => buildRequestWith(outputOverrides);

  useEffect(() => {
    if (didAutoPreviewRef.current) return;
    didAutoPreviewRef.current = true;
    commitMutation.reset();
    mutation.mutate(buildRequest());
    // Run once on mount to show the initial preview immediately.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    commitMutation.reset();
    mutation.mutate(buildRequest());
  };

  const handleOutputOverrideChange = (qid: string, name: string, value: string) => {
    setOutputOverrides((current) => ({
      ...current,
      [qid]: {
        ...(current[qid] ?? {}),
        [name]: value,
      },
    }));
  };

  const handleOutputOverrideReset = (qid: string, name: string) => {
    setOutputOverrides((current) => {
      const parameters = current[qid];
      if (!parameters || !(name in parameters)) return current;
      const { [name]: _removed, ...rest } = parameters;
      const next = { ...current, [qid]: rest };
      if (Object.keys(rest).length === 0) delete next[qid];
      return next;
    });
  };

  const handleTogglePick = (qid: string) => {
    setPickTargetQid((current) => (current === qid ? null : qid));
  };

  const outputOverrideRows = buildOutputOverrideRows(
    mutation.data?.data?.affected_qubits ?? [],
    outputOverrides,
  );

  const handlePlotClick = (event: PlotMouseEvent) => {
    const point = event.points?.[0];
    if (!point) return;
    // The spectroscopy map is frequency (x) against readout power (y): one click gives both.
    const x = typeof point.x === "number" ? point.x : Number(point.x);
    const y = typeof point.y === "number" ? point.y : Number(point.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;
    applyPickedPoint(x, y);
  };

  const commitRows: CommitParameterRow[] = outputOverrideRows.map((row) => ({
    ...row,
    value: parseFloatOrNull(row.value),
  }));
  const canCommitAllMuxQubits =
    commitRows.length > 0 && commitRows.every((row) => row.value !== null);

  const handleCommit = () => {
    setIsCommitConfirmOpen(true);
  };

  const handleConfirmCommit = () => {
    if (!canCommitAllMuxQubits) return;
    setIsCommitConfirmOpen(false);
    commitMutation.mutate(buildRequest());
  };

  // Reset drops the edits and re-runs the plain analysis, since the table is the only input.
  const handleReset = () => {
    setOutputOverrides({});
    setPickTargetQid(null);
    setIsCommitConfirmOpen(false);
    commitMutation.reset();
    mutation.mutate(buildRequestWith({}));
  };

  return (
    <>
      <PanelShell
        title="Re-analyze Resonator Spectroscopy"
        onReset={handleReset}
        onSubmit={handleSubmit}
        mutation={mutation}
        commitMutation={commitMutation}
        onCommit={handleCommit}
        onPlotClick={handlePlotClick}
        preferRawFigure
        outputRows={outputOverrideRows}
        onOutputChange={handleOutputOverrideChange}
        onOutputReset={handleOutputOverrideReset}
        pickTargetQid={pickTargetQid}
        onTogglePick={handleTogglePick}
      />
      <CommitParametersModal
        isOpen={isCommitConfirmOpen}
        isPending={commitMutation.isPending}
        rows={commitRows}
        onClose={() => setIsCommitConfirmOpen(false)}
        onConfirm={handleConfirmCommit}
      />
    </>
  );
}

// ── Qubit-spectroscopy panel ──────────────────────────────────────────────

interface QubitParamForm {
  binarize_threshold_sigma_plus: string;
  binarize_threshold_sigma_minus: string;
  top_power: string;
  f01_height_min: string;
  f12_distance_min: string;
  f12_distance_max: string;
  f12_height_min: string;
  retry_with_trim: boolean;
}

const DEFAULT_QUBIT_FORM: QubitParamForm = {
  binarize_threshold_sigma_plus: "",
  binarize_threshold_sigma_minus: "",
  top_power: "",
  f01_height_min: "",
  f12_distance_min: "",
  f12_distance_max: "",
  f12_height_min: "",
  retry_with_trim: false,
};

function QubitReanalysis({
  chipId,
  qubitId,
  sourceTaskId,
}: Omit<ReanalysisPanelProps, "taskName">) {
  const [form, setForm] = useState<QubitParamForm>(DEFAULT_QUBIT_FORM);
  const mutation = useReanalyzeQubitSpectroscopy();

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const params: ReanalyzeQubitSpectroscopyParams = {
      binarize_threshold_sigma_plus: parseFloatOrNull(form.binarize_threshold_sigma_plus),
      binarize_threshold_sigma_minus: parseFloatOrNull(form.binarize_threshold_sigma_minus),
      top_power: parseFloatOrNull(form.top_power),
      f01_height_min: parseFloatOrNull(form.f01_height_min),
      f12_distance_min: parseFloatOrNull(form.f12_distance_min),
      f12_distance_max: parseFloatOrNull(form.f12_distance_max),
      f12_height_min: parseFloatOrNull(form.f12_height_min),
      retry_with_trim: form.retry_with_trim || null,
    };
    mutation.mutate({
      chipId,
      qid: qubitId,
      data: {
        source_task_id: sourceTaskId ?? null,
        parameters: params,
      },
    });
  };

  const handleReset = () => {
    setForm(DEFAULT_QUBIT_FORM);
    mutation.reset();
  };

  return (
    <PanelShell
      title="Re-analyze Qubit Spectroscopy"
      onReset={handleReset}
      onSubmit={handleSubmit}
      mutation={mutation}
    >
      <NumberField
        label="binarize_threshold_sigma_plus"
        value={form.binarize_threshold_sigma_plus}
        placeholder="3.0"
        onChange={(v) => setForm({ ...form, binarize_threshold_sigma_plus: v })}
      />
      <NumberField
        label="binarize_threshold_sigma_minus"
        value={form.binarize_threshold_sigma_minus}
        placeholder="-2.0"
        onChange={(v) => setForm({ ...form, binarize_threshold_sigma_minus: v })}
      />
      <NumberField
        label="top_power (dB)"
        value={form.top_power}
        placeholder="0"
        onChange={(v) => setForm({ ...form, top_power: v })}
      />
      <NumberField
        label="f01_height_min (dB)"
        value={form.f01_height_min}
        placeholder="14.9"
        onChange={(v) => setForm({ ...form, f01_height_min: v })}
      />
      <NumberField
        label="f12_distance_min (GHz)"
        value={form.f12_distance_min}
        placeholder="0.125"
        onChange={(v) => setForm({ ...form, f12_distance_min: v })}
      />
      <NumberField
        label="f12_distance_max (GHz)"
        value={form.f12_distance_max}
        placeholder="0.5"
        onChange={(v) => setForm({ ...form, f12_distance_max: v })}
      />
      <NumberField
        label="f12_height_min (dB)"
        value={form.f12_height_min}
        placeholder="14.9"
        onChange={(v) => setForm({ ...form, f12_height_min: v })}
      />
      <CheckboxField
        label="retry_with_trim"
        value={form.retry_with_trim}
        onChange={(v) => setForm({ ...form, retry_with_trim: v })}
      />
    </PanelShell>
  );
}

// ── Shared panel chrome ───────────────────────────────────────────────────

interface ReanalyzeOutputParameterLike {
  name: string;
  value: number;
  unit?: string;
  current_value?: number | null;
  snapshot_value?: number | null;
  derived_from?: string | null;
}

interface ReanalyzeMutationLike {
  isPending: boolean;
  isError: boolean;
  error: unknown;
  data?:
    | {
        data?: {
          figure: unknown;
          raw_figure?: unknown;
          output_parameters: ReanalyzeOutputParameterLike[];
          affected_qubits?: {
            qid: string;
            output_parameters: ReanalyzeOutputParameterLike[];
          }[];
          source_task_id: string;
          committed?: boolean;
        };
      }
    | undefined;
}

interface PanelShellProps {
  title: string;
  /** Analysis parameters rendered above the result. Omitted when the table is the only input. */
  children?: React.ReactNode;
  mutation: ReanalyzeMutationLike;
  commitMutation?: ReanalyzeMutationLike;
  onSubmit: (e: React.FormEvent) => void;
  onReset: () => void;
  onCommit?: () => void;
  onPlotClick?: (event: PlotMouseEvent) => void;
  /** Show the unmarked figure with only the manual markers instead of the marked one. */
  preferRawFigure?: boolean;
  /** Editable output-parameter rows. When given, the result table becomes the edit surface. */
  outputRows?: OutputParameterEditRow[];
  onOutputChange?: (qid: string, name: string, value: string) => void;
  /** Drops the user's value so the row follows the analysis again. */
  onOutputReset?: (qid: string, name: string) => void;
  /** `${qid}-${name}` armed to receive the next value picked from a plot. */
  /** qid armed to receive the next point picked from the plot. */
  pickTargetQid?: string | null;
  onTogglePick?: (qid: string) => void;
}

function PanelShell({
  title,
  children,
  mutation,
  commitMutation,
  onSubmit,
  onReset,
  onCommit,
  onPlotClick,
  preferRawFigure,
  outputRows,
  onOutputChange,
  onOutputReset,
  pickTargetQid,
  onTogglePick,
}: PanelShellProps) {
  const result = commitMutation?.data?.data ?? mutation.data?.data;
  const canCommit = Boolean(onCommit && mutation.data?.data && !result?.committed);
  return (
    <div className="card bg-base-100 shadow-md border border-base-300">
      <div className="card-body p-4">
        <div className="flex items-center justify-between mb-2">
          <h4 className="font-semibold">{title}</h4>
          <span className="badge badge-ghost badge-sm">Preview first</span>
        </div>
        <p className="text-xs text-base-content/60 mb-3">
          Re-runs the analysis on the stored spectroscopy figure. Edit a value in the table to
          override it, Preview to redraw, then confirm to write the values to DB.
        </p>

        <form onSubmit={onSubmit} className="space-y-3">
          {children && <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">{children}</div>}

          {mutation.isError && (
            <div className="alert alert-error text-sm">
              <span>Reanalysis failed: {(mutation.error as Error)?.message ?? "unknown"}</span>
            </div>
          )}

          {commitMutation?.isError && (
            <div className="alert alert-error text-sm">
              <span>Commit failed: {(commitMutation.error as Error)?.message ?? "unknown"}</span>
            </div>
          )}

          {result && (
            <ReanalysisResult
              result={result}
              onPlotClick={onPlotClick}
              preferRawFigure={preferRawFigure}
              outputRows={outputRows}
              onOutputChange={onOutputChange}
              onOutputReset={onOutputReset}
              pickTargetQid={pickTargetQid}
              onTogglePick={onTogglePick}
            />
          )}

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              className="btn btn-sm btn-ghost gap-2"
              onClick={onReset}
              disabled={mutation.isPending || commitMutation?.isPending}
            >
              <RotateCcw size={14} />
              Reset
            </button>
            <button
              type="submit"
              className="btn btn-sm btn-primary"
              disabled={mutation.isPending || commitMutation?.isPending}
            >
              {mutation.isPending ? (
                <span className="loading loading-spinner loading-xs" />
              ) : (
                "Preview"
              )}
            </button>
            {canCommit && (
              <button
                type="button"
                className="btn btn-sm btn-warning"
                disabled={commitMutation?.isPending}
                onClick={onCommit}
              >
                {commitMutation?.isPending ? (
                  <span className="loading loading-spinner loading-xs" />
                ) : (
                  "Confirm DB Update"
                )}
              </button>
            )}
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Result rendering ──────────────────────────────────────────────────────

interface ReanalysisResultProps {
  result: NonNullable<NonNullable<ReanalyzeMutationLike["data"]>["data"]>;
  onPlotClick?: (event: PlotMouseEvent) => void;
  outputRows?: OutputParameterEditRow[];
  onOutputChange?: (qid: string, name: string, value: string) => void;
  onOutputReset?: (qid: string, name: string) => void;
  /** qid armed to receive the next point picked from the plot. */
  pickTargetQid?: string | null;
  onTogglePick?: (qid: string) => void;
  /**
   * Show the unmarked figure carrying only the manual markers. The task's own marked figure
   * already sits above the panel, so repeating the auto-detected peaks adds nothing.
   */
  preferRawFigure?: boolean;
}

function ReanalysisResult({
  result,
  onPlotClick,
  outputRows,
  onOutputChange,
  onOutputReset,
  pickTargetQid,
  onTogglePick,
  preferRawFigure,
}: ReanalysisResultProps) {
  type FigureLike = {
    data?: unknown;
    layout?: { autosize?: boolean; [k: string]: unknown };
  } | null;

  const figure = result.figure as FigureLike;
  const rawFigure = (result.raw_figure ?? null) as FigureLike;
  const displayFigure = preferRawFigure && rawFigure?.data ? rawFigure : figure;

  const displayLayout = useMemo(
    () => ({
      ...(displayFigure?.layout ?? {}),
      autosize: false,
    }),
    [displayFigure],
  );

  return (
    <div className="mt-4 space-y-3">
      <div>
        <div className="text-xs text-base-content/60 mb-1">
          source_task_id: <span className="font-mono">{result.source_task_id.slice(-12)}</span>
        </div>
      </div>

      {displayFigure?.data ? (
        <div className="max-w-full overflow-x-auto pb-2">
          <section className="min-w-[min(88vw,760px)] max-w-[88vw]">
            <div className="bg-base-200 rounded-lg p-2 flex justify-center overflow-auto max-h-[55vh]">
              <Plot
                // eslint-disable-next-line @typescript-eslint/no-explicit-any
                data={displayFigure.data as any}
                layout={displayLayout}
                config={{ displayModeBar: true, responsive: false }}
                useResizeHandler={false}
                onClick={onPlotClick}
                style={{ width: "auto", height: "auto" }}
              />
            </div>
          </section>
        </div>
      ) : (
        <div className="text-sm text-base-content/60">No figure returned from the server.</div>
      )}

      {result.committed && <div className="alert alert-success text-sm">Committed to DB.</div>}

      {outputRows && onOutputChange ? (
        <OutputParameterTable
          title="MUX affected qubits"
          description="Snapshot is what the source experiment produced, Current is the calibration DB value now, and New is what a DB update writes. Type a value directly, or press Take from plot on a qubit and click a point on the figure — one click sets its readout_frequency and optimal_power together, and readout_amplitude follows."
          rows={outputRows}
          onChange={onOutputChange}
          onReset={onOutputReset}
          isPickTarget={(row) => row.qid === pickTargetQid}
          canPick={(row) => row.name === PICKED_FROM_PLOT.x}
          onTogglePick={onTogglePick}
          pickHint="frequency and power"
        />
      ) : (
        <OutputParameterTable
          title="Output parameters"
          rows={toOutputRows(result.output_parameters)}
          showQubit={false}
          emptyMessage="No outputs (e.g. no f01 detected)."
        />
      )}
    </div>
  );
}

function toOutputRows(outputs: ReanalyzeOutputParameterLike[]): OutputParameterEditRow[] {
  return outputs.map((output) => ({
    qid: "",
    name: output.name,
    unit: output.unit,
    currentValue: output.current_value,
    snapshotValue: output.snapshot_value,
    derivedFrom: output.derived_from ?? undefined,
    value: formatOutputValue(output.value),
  }));
}

/**
 * Only values the user actually edited are sent. Untouched parameters keep whatever the
 * re-analysis computes, so a stale override never masks a fresh result.
 */
function numericOverrides(
  outputOverrides: OutputOverrideForm,
): Record<string, Record<string, number>> | null {
  const overrides: Record<string, Record<string, number>> = {};

  for (const [qid, parameters] of Object.entries(outputOverrides)) {
    for (const [name, rawValue] of Object.entries(parameters)) {
      const parsedValue = parseFloatOrNull(rawValue);
      if (parsedValue === null) continue;
      overrides[qid] = { ...(overrides[qid] ?? {}), [name]: parsedValue };
    }
  }

  return Object.keys(overrides).length > 0 ? overrides : null;
}

function buildOutputOverrideRows(
  affectedQubits: NonNullable<
    NonNullable<NonNullable<ReanalyzeMutationLike["data"]>["data"]>["affected_qubits"]
  >,
  outputOverrides: OutputOverrideForm,
): OutputParameterEditRow[] {
  return affectedQubits.flatMap((affected) =>
    affected.output_parameters.map((parameter) => {
      const source = parameter.derived_from;
      if (source) {
        // Show what the edited source implies right away, without waiting for a preview.
        const sourceOverride = parseFloatOrNull(outputOverrides[affected.qid]?.[source] ?? "");
        const value =
          parameter.name === "readout_amplitude" && sourceOverride !== null
            ? readoutAmplitudeForPower(sourceOverride)
            : parameter.value;
        return {
          qid: affected.qid,
          name: parameter.name,
          unit: parameter.unit,
          currentValue: parameter.current_value,
          snapshotValue: parameter.snapshot_value,
          analyzedValue: parameter.value,
          derivedFrom: source,
          value: formatOutputValue(value),
        };
      }

      // undefined means untouched. An empty string is a value the user cleared on the way to
      // typing a new one, so it must survive instead of snapping back to the analyzed value.
      const override = outputOverrides[affected.qid]?.[parameter.name];
      return {
        qid: affected.qid,
        name: parameter.name,
        unit: parameter.unit,
        currentValue: parameter.current_value,
        snapshotValue: parameter.snapshot_value,
        analyzedValue: parameter.value,
        edited: override !== undefined,
        value: override ?? formatOutputValue(parameter.value),
      };
    }),
  );
}

/** Mirrors ReanalysisService._readout_amplitude_for_power. */
function readoutAmplitudeForPower(optimalPower: number): number {
  return 10 ** (optimalPower / 20);
}

// ── Form primitives ───────────────────────────────────────────────────────

interface NumberFieldProps {
  label: string;
  value: string;
  placeholder?: string;
  hint?: string;
  disabled?: boolean;
  onChange: (v: string) => void;
}

function NumberField({ label, value, placeholder, hint, disabled, onChange }: NumberFieldProps) {
  return (
    <label className="form-control">
      <span className="label-text text-xs font-mono">{label}</span>
      <input
        type="number"
        step="any"
        className="input input-sm input-bordered w-full"
        value={value}
        placeholder={placeholder}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
      />
      {hint && <span className="label-text-alt text-base-content/60">{hint}</span>}
    </label>
  );
}

interface CheckboxFieldProps {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
}

function CheckboxField({ label, value, onChange }: CheckboxFieldProps) {
  return (
    <label className="label cursor-pointer justify-start gap-3">
      <input
        type="checkbox"
        className="checkbox checkbox-sm"
        checked={value}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="label-text text-xs font-mono">{label}</span>
    </label>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────
