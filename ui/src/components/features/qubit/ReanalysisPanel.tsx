"use client";

import React, { useId, useMemo } from "react";

import { zodResolver } from "@hookform/resolvers/zod";
import { RotateCcw, Sparkles } from "lucide-react";
import dynamic from "next/dynamic";
import { useForm, type UseFormRegisterReturn } from "react-hook-form";
import { z } from "zod";

import type {
  ReanalyzeQubitSpectroscopyParams,
  ReanalyzeResonatorSpectroscopyParams,
} from "@/schemas";

import {
  useReanalyzeQubitSpectroscopy,
  useReanalyzeResonatorSpectroscopy,
} from "@/client/chip/chip";
import { SelectedLabel } from "@/components/ui/SelectedLabel";

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

/** Renders the reanalysis form matching the task, or nothing for unsupported tasks. */
export function ReanalysisPanel({ chipId, qubitId, taskName, sourceTaskId }: ReanalysisPanelProps) {
  const kind: ReanalyzeKind | null =
    taskName === RESONATOR_TASK ? "resonator" : taskName === QUBIT_TASK ? "qubit" : null;

  if (!kind) return null;

  return kind === "resonator" ? (
    <ResonatorReanalysis chipId={chipId} qubitId={qubitId} sourceTaskId={sourceTaskId} />
  ) : (
    <QubitReanalysis chipId={chipId} qubitId={qubitId} sourceTaskId={sourceTaskId} />
  );
}

// ── Schema helpers ────────────────────────────────────────────────────────

const NUMBER_ERROR = "Must be a number";
const POSITIVE_INTEGER_ERROR = "Must be a positive integer";

/** Converts a numeric text field to a number, or null when empty. */
function toNumberOrNull(value: string): number | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : Number(trimmed);
}

/** Adds a field issue when a non-empty numeric text field is not a finite number. */
function checkNumber(ctx: z.RefinementCtx, field: string, value: string) {
  const parsed = toNumberOrNull(value);
  if (parsed !== null && !Number.isFinite(parsed)) {
    ctx.addIssue({ code: "custom", path: [field], message: NUMBER_ERROR });
  }
}

// ── Resonator-spectroscopy panel ──────────────────────────────────────────

const resonatorFormSchema = z
  .object({
    num_resonators: z.string(),
    high_power_min: z.string(),
    high_power_max: z.string(),
    low_power: z.string(),
    bare_shift_estimator_type: z.enum(["", "config", "high_frequency_strength"]),
    bare_shift_strength_limit: z.string(),
  })
  .superRefine((values, ctx) => {
    const numResonators = toNumberOrNull(values.num_resonators);
    if (numResonators !== null && !(Number.isInteger(numResonators) && numResonators >= 1)) {
      ctx.addIssue({
        code: "custom",
        path: ["num_resonators"],
        message: POSITIVE_INTEGER_ERROR,
      });
    }
    if (values.bare_shift_estimator_type === "high_frequency_strength") {
      checkNumber(ctx, "bare_shift_strength_limit", values.bare_shift_strength_limit);
    } else {
      checkNumber(ctx, "high_power_min", values.high_power_min);
      checkNumber(ctx, "high_power_max", values.high_power_max);
      checkNumber(ctx, "low_power", values.low_power);
    }
  })
  .transform((values): ReanalyzeResonatorSpectroscopyParams => {
    const usingAutoBoundary = values.bare_shift_estimator_type === "high_frequency_strength";
    return {
      num_resonators: toNumberOrNull(values.num_resonators),
      high_power_min: usingAutoBoundary ? null : toNumberOrNull(values.high_power_min),
      high_power_max: usingAutoBoundary ? null : toNumberOrNull(values.high_power_max),
      low_power: usingAutoBoundary ? null : toNumberOrNull(values.low_power),
      bare_shift_estimator_type: values.bare_shift_estimator_type || null,
      bare_shift_strength_limit: usingAutoBoundary
        ? toNumberOrNull(values.bare_shift_strength_limit)
        : null,
    };
  });

type ResonatorFormInput = z.input<typeof resonatorFormSchema>;
type ResonatorFormOutput = z.output<typeof resonatorFormSchema>;

const DEFAULT_RESONATOR_FORM: ResonatorFormInput = {
  num_resonators: "",
  high_power_min: "",
  high_power_max: "",
  low_power: "",
  bare_shift_estimator_type: "",
  bare_shift_strength_limit: "",
};

/** Form that previews a resonator-spectroscopy reanalysis with parameter overrides. */
function ResonatorReanalysis({
  chipId,
  qubitId,
  sourceTaskId,
}: Omit<ReanalysisPanelProps, "taskName">) {
  const id = useId();
  const {
    register,
    handleSubmit,
    reset,
    watch,
    clearErrors,
    formState: { errors },
  } = useForm<ResonatorFormInput, unknown, ResonatorFormOutput>({
    resolver: zodResolver(resonatorFormSchema),
    defaultValues: DEFAULT_RESONATOR_FORM,
  });
  const mutation = useReanalyzeResonatorSpectroscopy();

  const usingAutoBoundary = watch("bare_shift_estimator_type") === "high_frequency_strength";

  /** Sends the validated parameters to the reanalysis mutation. */
  const onValid = (parameters: ResonatorFormOutput) => {
    mutation.mutate({
      chipId,
      qid: qubitId,
      data: {
        source_task_id: sourceTaskId ?? null,
        parameters,
      },
    });
  };

  /** Restores the default values and clears the mutation state. */
  const handleReset = () => {
    reset(DEFAULT_RESONATOR_FORM);
    mutation.reset();
  };

  return (
    <PanelShell
      title="Re-analyze Resonator Spectroscopy"
      onReset={handleReset}
      onSubmit={handleSubmit(onValid)}
      mutation={mutation}
    >
      <NumberField
        id={`${id}-num_resonators`}
        label="num_resonators"
        placeholder="4"
        error={errors.num_resonators?.message}
        registration={register("num_resonators")}
      />
      <SelectField
        id={`${id}-bare_shift_estimator_type`}
        label="bare_shift_estimator_type"
        error={errors.bare_shift_estimator_type?.message}
        registration={register("bare_shift_estimator_type", {
          onChange: (e: React.ChangeEvent<HTMLSelectElement>) =>
            clearErrors(
              e.target.value === "high_frequency_strength"
                ? ["high_power_min", "high_power_max", "low_power"]
                : "bare_shift_strength_limit",
            ),
        })}
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
        id={`${id}-high_power_min`}
        label="high_power_min (dB)"
        placeholder="-20"
        disabled={usingAutoBoundary}
        error={errors.high_power_min?.message}
        registration={register("high_power_min")}
      />
      <NumberField
        id={`${id}-high_power_max`}
        label="high_power_max (dB)"
        placeholder="0"
        disabled={usingAutoBoundary}
        error={errors.high_power_max?.message}
        registration={register("high_power_max")}
      />
      <NumberField
        id={`${id}-low_power`}
        label="low_power (dB)"
        placeholder="-30"
        disabled={usingAutoBoundary}
        error={errors.low_power?.message}
        registration={register("low_power")}
      />
      <NumberField
        id={`${id}-bare_shift_strength_limit`}
        label="bare_shift_strength_limit"
        placeholder="4.0"
        disabled={!usingAutoBoundary}
        error={errors.bare_shift_strength_limit?.message}
        registration={register("bare_shift_strength_limit")}
      />
    </PanelShell>
  );
}

// ── Qubit-spectroscopy panel ──────────────────────────────────────────────

const qubitFormSchema = z
  .object({
    binarize_threshold_sigma_plus: z.string(),
    binarize_threshold_sigma_minus: z.string(),
    top_power: z.string(),
    f01_height_min: z.string(),
    f12_distance_min: z.string(),
    f12_distance_max: z.string(),
    f12_height_min: z.string(),
    retry_with_trim: z.boolean(),
  })
  .superRefine((values, ctx) => {
    checkNumber(ctx, "binarize_threshold_sigma_plus", values.binarize_threshold_sigma_plus);
    checkNumber(ctx, "binarize_threshold_sigma_minus", values.binarize_threshold_sigma_minus);
    checkNumber(ctx, "top_power", values.top_power);
    checkNumber(ctx, "f01_height_min", values.f01_height_min);
    checkNumber(ctx, "f12_distance_min", values.f12_distance_min);
    checkNumber(ctx, "f12_distance_max", values.f12_distance_max);
    checkNumber(ctx, "f12_height_min", values.f12_height_min);
  })
  .transform((values): ReanalyzeQubitSpectroscopyParams => ({
    binarize_threshold_sigma_plus: toNumberOrNull(values.binarize_threshold_sigma_plus),
    binarize_threshold_sigma_minus: toNumberOrNull(values.binarize_threshold_sigma_minus),
    top_power: toNumberOrNull(values.top_power),
    f01_height_min: toNumberOrNull(values.f01_height_min),
    f12_distance_min: toNumberOrNull(values.f12_distance_min),
    f12_distance_max: toNumberOrNull(values.f12_distance_max),
    f12_height_min: toNumberOrNull(values.f12_height_min),
    retry_with_trim: values.retry_with_trim || null,
  }));

type QubitFormInput = z.input<typeof qubitFormSchema>;
type QubitFormOutput = z.output<typeof qubitFormSchema>;

const DEFAULT_QUBIT_FORM: QubitFormInput = {
  binarize_threshold_sigma_plus: "",
  binarize_threshold_sigma_minus: "",
  top_power: "",
  f01_height_min: "",
  f12_distance_min: "",
  f12_distance_max: "",
  f12_height_min: "",
  retry_with_trim: false,
};

/** Form that previews a qubit-spectroscopy reanalysis with parameter overrides. */
function QubitReanalysis({
  chipId,
  qubitId,
  sourceTaskId,
}: Omit<ReanalysisPanelProps, "taskName">) {
  const id = useId();
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<QubitFormInput, unknown, QubitFormOutput>({
    resolver: zodResolver(qubitFormSchema),
    defaultValues: DEFAULT_QUBIT_FORM,
  });
  const mutation = useReanalyzeQubitSpectroscopy();

  /** Sends the validated parameters to the reanalysis mutation. */
  const onValid = (parameters: QubitFormOutput) => {
    mutation.mutate({
      chipId,
      qid: qubitId,
      data: {
        source_task_id: sourceTaskId ?? null,
        parameters,
      },
    });
  };

  /** Restores the default values and clears the mutation state. */
  const handleReset = () => {
    reset(DEFAULT_QUBIT_FORM);
    mutation.reset();
  };

  return (
    <PanelShell
      title="Re-analyze Qubit Spectroscopy"
      onReset={handleReset}
      onSubmit={handleSubmit(onValid)}
      mutation={mutation}
    >
      <NumberField
        id={`${id}-binarize_threshold_sigma_plus`}
        label="binarize_threshold_sigma_plus"
        placeholder="3.0"
        error={errors.binarize_threshold_sigma_plus?.message}
        registration={register("binarize_threshold_sigma_plus")}
      />
      <NumberField
        id={`${id}-binarize_threshold_sigma_minus`}
        label="binarize_threshold_sigma_minus"
        placeholder="-2.0"
        error={errors.binarize_threshold_sigma_minus?.message}
        registration={register("binarize_threshold_sigma_minus")}
      />
      <NumberField
        id={`${id}-top_power`}
        label="top_power (dB)"
        placeholder="0"
        error={errors.top_power?.message}
        registration={register("top_power")}
      />
      <NumberField
        id={`${id}-f01_height_min`}
        label="f01_height_min (dB)"
        placeholder="14.9"
        error={errors.f01_height_min?.message}
        registration={register("f01_height_min")}
      />
      <NumberField
        id={`${id}-f12_distance_min`}
        label="f12_distance_min (GHz)"
        placeholder="0.125"
        error={errors.f12_distance_min?.message}
        registration={register("f12_distance_min")}
      />
      <NumberField
        id={`${id}-f12_distance_max`}
        label="f12_distance_max (GHz)"
        placeholder="0.5"
        error={errors.f12_distance_max?.message}
        registration={register("f12_distance_max")}
      />
      <NumberField
        id={`${id}-f12_height_min`}
        label="f12_height_min (dB)"
        placeholder="14.9"
        error={errors.f12_height_min?.message}
        registration={register("f12_height_min")}
      />
      <CheckboxField
        id={`${id}-retry_with_trim`}
        label="retry_with_trim"
        registration={register("retry_with_trim")}
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
  onSubmit: React.FormEventHandler<HTMLFormElement>;
  onReset: () => void;
}

/** Card chrome shared by the reanalysis forms: header, form, mutation error and result. */
function PanelShell({ title, children, mutation, onSubmit, onReset }: PanelShellProps) {
  return (
    <div className="card bg-base-100 shadow-md border border-base-300">
      <div className="card-body p-4">
        <div className="flex items-center justify-between mb-2">
          <h4 className="font-medium flex items-center gap-2">
            <Sparkles size={16} className="text-primary" />
            {title}
          </h4>
          <span className="badge badge-ghost badge-sm">Preview only</span>
        </div>
        <p className="text-xs text-base-content/60 mb-3">
          Re-runs the analysis on the stored spectroscopy figure with the given overrides. Empty
          fields fall back to the original task&apos;s parameters. The DB is not modified.
        </p>

        <form onSubmit={onSubmit} className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">{children}</div>
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
            <button type="submit" className="btn btn-sm btn-primary" disabled={mutation.isPending}>
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
            <span>Reanalysis failed: {(mutation.error as Error)?.message ?? "unknown"}</span>
          </div>
        )}

        {mutation.data?.data && <ReanalysisResult result={mutation.data.data} />}
      </div>
    </div>
  );
}

// ── Result rendering ──────────────────────────────────────────────────────

interface ReanalysisResultProps {
  result: NonNullable<NonNullable<ReanalyzeMutationLike["data"]>["data"]>;
}

/** Renders the figure and re-estimated outputs returned by a reanalysis. */
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
          source_task_id: <span className="font-mono">{result.source_task_id.slice(-12)}</span>
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
        <div className="text-sm text-base-content/60">No figure returned from the server.</div>
      )}

      <div>
        <div className="text-xs font-medium mb-1">Re-estimated outputs</div>
        {result.output_parameters.length === 0 ? (
          <div className="text-xs text-base-content/60">No outputs (e.g. no f01 detected).</div>
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

interface FieldErrorProps {
  id: string;
  error?: string;
}

/** Renders the inline validation message for a field. */
function FieldError({ id, error }: FieldErrorProps) {
  if (!error) return null;
  return (
    <p id={`${id}-error`} className="mt-1 text-sm text-error">
      {error}
    </p>
  );
}

interface NumberFieldProps {
  id: string;
  label: string;
  placeholder?: string;
  disabled?: boolean;
  error?: string;
  registration: UseFormRegisterReturn;
}

/** Labelled numeric input wired to React Hook Form with an inline error. */
function NumberField({ id, label, placeholder, disabled, error, registration }: NumberFieldProps) {
  return (
    <div className="form-control">
      <label htmlFor={id} className="label-text text-xs font-mono">
        {label}
      </label>
      <input
        id={id}
        type="number"
        step="any"
        className={`input input-sm input-bordered w-full ${error ? "input-error" : ""}`}
        placeholder={placeholder}
        disabled={disabled}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `${id}-error` : undefined}
        {...registration}
      />
      <FieldError id={id} error={error} />
    </div>
  );
}

interface SelectFieldProps {
  id: string;
  label: string;
  options: { value: string; label: string }[];
  error?: string;
  registration: UseFormRegisterReturn;
}

/** Labelled select wired to React Hook Form with an inline error. */
function SelectField({ id, label, options, error, registration }: SelectFieldProps) {
  return (
    <div className="form-control">
      <label htmlFor={id} className="label-text text-xs font-mono">
        {label}
      </label>
      <select
        id={id}
        className={`select select-sm select-bordered w-full ${error ? "select-error" : ""}`}
        aria-invalid={Boolean(error)}
        aria-describedby={error ? `${id}-error` : undefined}
        {...registration}
      >
        <SelectedLabel />
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <FieldError id={id} error={error} />
    </div>
  );
}

interface CheckboxFieldProps {
  id: string;
  label: string;
  registration: UseFormRegisterReturn;
}

/** Labelled checkbox wired to React Hook Form. */
function CheckboxField({ id, label, registration }: CheckboxFieldProps) {
  return (
    <label htmlFor={id} className="label cursor-pointer justify-start gap-3">
      <input id={id} type="checkbox" className="checkbox checkbox-sm" {...registration} />
      <span className="label-text text-xs font-mono">{label}</span>
    </label>
  );
}
