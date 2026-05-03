"use client";

import React, { useMemo, useState } from "react";

import dynamic from "next/dynamic";
import { RotateCcw, Sparkles } from "lucide-react";

import type {
  ReanalyzeQubitSpectroscopyParams,
  ReanalyzeResonatorSpectroscopyParams,
  ReanalyzeResonatorSpectroscopyParamsBareShiftEstimatorType,
} from "@/schemas";

import {
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
}

const RESONATOR_TASK = "CheckResonatorSpectroscopy";
const QUBIT_TASK = "CheckQubitSpectroscopy";

export function ReanalysisPanel({
  chipId,
  qubitId,
  taskName,
  sourceTaskId,
}: ReanalysisPanelProps) {
  const kind: ReanalyzeKind | null =
    taskName === RESONATOR_TASK
      ? "resonator"
      : taskName === QUBIT_TASK
        ? "qubit"
        : null;

  if (!kind) return null;

  return kind === "resonator" ? (
    <ResonatorReanalysis
      chipId={chipId}
      qubitId={qubitId}
      sourceTaskId={sourceTaskId}
    />
  ) : (
    <QubitReanalysis
      chipId={chipId}
      qubitId={qubitId}
      sourceTaskId={sourceTaskId}
    />
  );
}

// ── Resonator-spectroscopy panel ──────────────────────────────────────────

interface ResonatorParamForm {
  num_resonators: string;
  high_power_min: string;
  high_power_max: string;
  low_power: string;
  /** Empty string means "use whatever the original task ran with". */
  bare_shift_estimator_type: "" | "config" | "high_frequency_strength";
  bare_shift_strength_limit: string;
}

const DEFAULT_RESONATOR_FORM: ResonatorParamForm = {
  num_resonators: "",
  high_power_min: "",
  high_power_max: "",
  low_power: "",
  bare_shift_estimator_type: "",
  bare_shift_strength_limit: "",
};

function ResonatorReanalysis({
  chipId,
  qubitId,
  sourceTaskId,
}: Omit<ReanalysisPanelProps, "taskName">) {
  const [form, setForm] = useState<ResonatorParamForm>(DEFAULT_RESONATOR_FORM);
  const mutation = useReanalyzeResonatorSpectroscopy();

  const usingAutoBoundary =
    form.bare_shift_estimator_type === "high_frequency_strength";

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const params: ReanalyzeResonatorSpectroscopyParams = {
      num_resonators: parseInt(form.num_resonators) || null,
      high_power_min: usingAutoBoundary
        ? null
        : parseFloatOrNull(form.high_power_min),
      high_power_max: usingAutoBoundary
        ? null
        : parseFloatOrNull(form.high_power_max),
      low_power: usingAutoBoundary ? null : parseFloatOrNull(form.low_power),
      bare_shift_estimator_type:
        (form.bare_shift_estimator_type as ReanalyzeResonatorSpectroscopyParamsBareShiftEstimatorType) ||
        null,
      bare_shift_strength_limit: usingAutoBoundary
        ? parseFloatOrNull(form.bare_shift_strength_limit)
        : null,
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
    setForm(DEFAULT_RESONATOR_FORM);
    mutation.reset();
  };

  return (
    <PanelShell
      title="Re-analyze Resonator Spectroscopy"
      onReset={handleReset}
      onSubmit={handleSubmit}
      mutation={mutation}
    >
      <NumberField
        label="num_resonators"
        value={form.num_resonators}
        placeholder="4"
        onChange={(v) => setForm({ ...form, num_resonators: v })}
      />
      <SelectField
        label="bare_shift_estimator_type"
        value={form.bare_shift_estimator_type}
        onChange={(v) =>
          setForm({
            ...form,
            bare_shift_estimator_type:
              v as ResonatorParamForm["bare_shift_estimator_type"],
          })
        }
        options={[
          { value: "", label: "(use original task setting)" },
          {
            value: "config",
            label: "manual — specify high/low power explicitly",
          },
          {
            value: "high_frequency_strength",
            label: "auto — detect from FFT energy",
          },
        ]}
      />
      <NumberField
        label="high_power_min (dB)"
        value={form.high_power_min}
        placeholder="-20"
        disabled={usingAutoBoundary}
        onChange={(v) => setForm({ ...form, high_power_min: v })}
      />
      <NumberField
        label="high_power_max (dB)"
        value={form.high_power_max}
        placeholder="0"
        disabled={usingAutoBoundary}
        onChange={(v) => setForm({ ...form, high_power_max: v })}
      />
      <NumberField
        label="low_power (dB)"
        value={form.low_power}
        placeholder="-30"
        disabled={usingAutoBoundary}
        onChange={(v) => setForm({ ...form, low_power: v })}
      />
      <NumberField
        label="bare_shift_strength_limit"
        value={form.bare_shift_strength_limit}
        placeholder="4.0"
        disabled={!usingAutoBoundary}
        onChange={(v) => setForm({ ...form, bare_shift_strength_limit: v })}
      />
    </PanelShell>
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
      binarize_threshold_sigma_plus: parseFloatOrNull(
        form.binarize_threshold_sigma_plus,
      ),
      binarize_threshold_sigma_minus: parseFloatOrNull(
        form.binarize_threshold_sigma_minus,
      ),
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
        onChange={(v) =>
          setForm({ ...form, binarize_threshold_sigma_minus: v })
        }
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

interface ReanalyzeMutationLike {
  isPending: boolean;
  isError: boolean;
  error: unknown;
  data?:
    | {
        data?: {
          figure: unknown;
          output_parameters: { name: string; value: number; unit?: string }[];
          source_task_id: string;
        };
      }
    | undefined;
}

interface PanelShellProps {
  title: string;
  children: React.ReactNode;
  mutation: ReanalyzeMutationLike;
  onSubmit: (e: React.FormEvent) => void;
  onReset: () => void;
}

function PanelShell({
  title,
  children,
  mutation,
  onSubmit,
  onReset,
}: PanelShellProps) {
  return (
    <div className="card bg-base-100 shadow-md border border-base-300">
      <div className="card-body p-4">
        <div className="flex items-center justify-between mb-2">
          <h4 className="font-semibold flex items-center gap-2">
            <Sparkles size={16} className="text-primary" />
            {title}
          </h4>
          <span className="badge badge-ghost badge-sm">Preview only</span>
        </div>
        <p className="text-xs text-base-content/60 mb-3">
          Re-runs the analysis on the stored spectroscopy figure with the given
          overrides. Empty fields fall back to the original task&apos;s
          parameters. The DB is not modified.
        </p>

        <form onSubmit={onSubmit} className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {children}
          </div>
          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              className="btn btn-sm btn-ghost gap-2"
              onClick={onReset}
              disabled={mutation.isPending}
            >
              <RotateCcw size={14} />
              Reset
            </button>
            <button
              type="submit"
              className="btn btn-sm btn-primary"
              disabled={mutation.isPending}
            >
              {mutation.isPending ? (
                <span className="loading loading-spinner loading-xs" />
              ) : (
                "Preview"
              )}
            </button>
          </div>
        </form>

        {mutation.isError && (
          <div className="alert alert-error mt-3 text-sm">
            <span>
              Reanalysis failed:{" "}
              {(mutation.error as Error)?.message ?? "unknown"}
            </span>
          </div>
        )}

        {mutation.data?.data && (
          <ReanalysisResult result={mutation.data.data} />
        )}
      </div>
    </div>
  );
}

// ── Result rendering ──────────────────────────────────────────────────────

interface ReanalysisResultProps {
  result: NonNullable<NonNullable<ReanalyzeMutationLike["data"]>["data"]>;
}

function ReanalysisResult({ result }: ReanalysisResultProps) {
  const figure = result.figure as {
    data?: unknown;
    layout?: { autosize?: boolean; [k: string]: unknown };
  } | null;

  const layout = useMemo(
    () => ({
      ...(figure?.layout ?? {}),
      autosize: false,
    }),
    [figure],
  );

  return (
    <div className="mt-4 space-y-3">
      <div>
        <div className="text-xs text-base-content/60 mb-1">
          source_task_id:{" "}
          <span className="font-mono">{result.source_task_id.slice(-12)}</span>
        </div>
      </div>

      {figure?.data ? (
        <div className="bg-base-200 rounded-lg p-2 flex justify-center overflow-x-auto">
          <Plot
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            data={figure.data as any}
            layout={layout}
            config={{ displayModeBar: true, responsive: false }}
            useResizeHandler={false}
            style={{ width: "auto", height: "auto" }}
          />
        </div>
      ) : (
        <div className="text-sm text-base-content/60">
          No figure returned from the server.
        </div>
      )}

      <div>
        <div className="text-xs font-semibold mb-1">Re-estimated outputs</div>
        {result.output_parameters.length === 0 ? (
          <div className="text-xs text-base-content/60">
            No outputs (e.g. no f01 detected).
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="table table-zebra table-xs">
              <thead>
                <tr>
                  <th>Parameter</th>
                  <th>Value</th>
                  <th>Unit</th>
                </tr>
              </thead>
              <tbody>
                {result.output_parameters.map((p) => (
                  <tr key={p.name}>
                    <td className="font-medium">{p.name}</td>
                    <td className="font-mono">
                      {Number.isFinite(p.value) ? p.value.toFixed(6) : "-"}
                    </td>
                    <td>{p.unit || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Form primitives ───────────────────────────────────────────────────────

interface NumberFieldProps {
  label: string;
  value: string;
  placeholder?: string;
  disabled?: boolean;
  onChange: (v: string) => void;
}

function NumberField({
  label,
  value,
  placeholder,
  disabled,
  onChange,
}: NumberFieldProps) {
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
    </label>
  );
}

interface SelectFieldProps {
  label: string;
  value: string;
  options: { value: string; label: string }[];
  onChange: (v: string) => void;
}

function SelectField({ label, value, options, onChange }: SelectFieldProps) {
  return (
    <label className="form-control">
      <span className="label-text text-xs font-mono">{label}</span>
      <select
        className="select select-sm select-bordered w-full"
        value={value}
        onChange={(e) => onChange(e.target.value)}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
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

function parseFloatOrNull(s: string): number | null {
  if (s === "") return null;
  const n = Number(s);
  return Number.isFinite(n) ? n : null;
}
