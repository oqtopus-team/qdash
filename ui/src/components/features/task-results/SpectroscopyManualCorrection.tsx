"use client";

import { CalibrationGitHubSyncNotice } from "@/components/features/task-results/CalibrationGitHubSyncNotice";
import type { ManualParameterUpdateResponse } from "@/schemas";

import { useId, useMemo, useState } from "react";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Crosshair, Pencil, RotateCcw, X } from "lucide-react";
import type { PlotMouseEvent } from "plotly.js";
import { useForm, useWatch } from "react-hook-form";
import { z } from "zod";

import { useUpdateCalibrationParameters } from "@/client/calibration/calibration";
import { getGetChipQubitQueryKey, useGetChipQubit } from "@/client/chip/chip";
import { getGetTaskResultQueryKey } from "@/client/task/task";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import { PlotlyRenderer } from "@/components/charts/PlotlyRenderer";
import { getApiErrorMessage } from "@/lib/utils/apiError";

const PARAMETER_UNITS: Record<string, string> = {
  readout_frequency: "GHz",
  readout_amplitude: "a.u.",
  control_frequency: "GHz",
  coarse_control_amplitude: "a.u.",
};

/**
 * Operational parameters an operator may correct from each spectroscopy result, mapped to
 * the source output they are read from. Measured values (`resonator_frequency`,
 * `coarse_qubit_frequency`) and diagnostics are never corrected by hand; see
 * docs/developer-guide/workflow/frequency-parameter-policy.md.
 */
const CORRECTION_PARAMETERS: Record<string, Readonly<Record<string, string>>> = {
  CheckResonatorSpectroscopy: {
    readout_frequency: "resonator_frequency",
    readout_amplitude: "readout_amplitude",
  },
  CheckQubitSpectroscopy: {
    control_frequency: "coarse_qubit_frequency",
    coarse_control_amplitude: "coarse_control_amplitude",
  },
};

/** Headroom applied by CheckQubitSpectroscopy when deriving the coarse drive amplitude. */
const COARSE_CONTROL_AMPLITUDE_HEADROOM_DB = 10;

interface SpectroscopyManualCorrectionProps {
  chipId: string;
  qid: string;
  taskId: string;
  taskName: string;
  outputParameters: Record<string, unknown>;
  jsonFigurePaths: string[];
}

interface PickedPoint {
  x: number;
  y: number;
}

type CorrectionFormInput = Record<string, string>;
type CorrectionFormOutput = Record<string, number>;

const INVALID_NUMBER_ERROR = "Enter a finite number";
const NO_CHANGE_ERROR = "Change one or more values to continue.";

/** Manually correct spectroscopy outputs while retaining the source Task Result. */
export function SpectroscopyManualCorrection({
  chipId,
  qid,
  taskId,
  taskName,
  outputParameters,
  jsonFigurePaths,
}: SpectroscopyManualCorrectionProps) {
  const [baselines, setBaselines] = useState<Record<string, number | null> | null>(null);
  const [createdTaskId, setCreatedTaskId] = useState<string | null>(null);
  const [githubResult, setGithubResult] = useState<ManualParameterUpdateResponse | null>(null);
  const queryClient = useQueryClient();
  const { data: qubitResponse } = useGetChipQubit(chipId, qid);

  const names = useMemo(() => spectroscopyCorrectionParameterNames(taskName), [taskName]);
  const currentData = (qubitResponse?.data?.data ?? {}) as Record<string, unknown>;
  const measuredOutput = (name: string) => outputParameters[sourceOutputName(taskName, name)];

  /** Captures the comparison baselines and opens the correction form. */
  const beginEditing = () => {
    setBaselines(
      Object.fromEntries(
        names.map((name) => [
          name,
          parameterValue(currentData[name]) ?? parameterValue(measuredOutput(name)),
        ]),
      ),
    );
  };

  /** Shows the saved correction and refreshes the qubit and source result. */
  const handleSaved = (response: ManualParameterUpdateResponse) => {
    setGithubResult(response);
    setBaselines(null);
    setCreatedTaskId(response.task_id);
    void queryClient.invalidateQueries({ queryKey: getGetChipQubitQueryKey(chipId, qid) });
    void queryClient.invalidateQueries({ queryKey: getGetTaskResultQueryKey(taskId) });
  };

  if (!baselines) {
    return (
      <div className="rounded-[var(--radius-box)] border border-base-300 bg-base-100 p-4 shadow-sm">
        {createdTaskId && (
          <div className="alert alert-success mb-4 text-sm">
            <span>Manual correction saved.</span>
            <a className="btn btn-sm btn-ghost" href={`/task-results/${createdTaskId}`}>
              View correction result
            </a>
          </div>
        )}
        {githubResult && (
          <CalibrationGitHubSyncNotice key={githubResult.task_id} result={githubResult} />
        )}
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex min-w-0 items-start gap-3">
            <div className="rounded-lg bg-base-200 p-2 text-base-content/70">
              <Pencil size={16} />
            </div>
            <div className="min-w-0">
              <h3 className="text-sm font-medium">Manual correction</h3>
              <p className="mt-0.5 text-xs leading-relaxed text-base-content/60">
                Correct a misassigned spectroscopy result without changing the original result or
                running analysis again.
              </p>
            </div>
          </div>
          <button className="btn btn-sm btn-outline shrink-0" onClick={beginEditing}>
            <Pencil data-icon="inline-start" />
            Correct values
          </button>
        </div>
      </div>
    );
  }

  return (
    <SpectroscopyCorrectionEditor
      chipId={chipId}
      qid={qid}
      taskId={taskId}
      taskName={taskName}
      names={names}
      baselines={baselines}
      currentData={currentData}
      measuredOutput={measuredOutput}
      jsonFigurePaths={jsonFigurePaths}
      onClose={() => setBaselines(null)}
      onSaved={handleSaved}
    />
  );
}

interface SpectroscopyCorrectionEditorProps {
  chipId: string;
  qid: string;
  taskId: string;
  taskName: string;
  names: string[];
  baselines: Record<string, number | null>;
  currentData: Record<string, unknown>;
  measuredOutput: (name: string) => unknown;
  jsonFigurePaths: string[];
  onClose: () => void;
  onSaved: (response: ManualParameterUpdateResponse) => void;
}

/** Correction table, review dialog, and plot picker for one editing session. */
function SpectroscopyCorrectionEditor({
  chipId,
  qid,
  taskId,
  taskName,
  names,
  baselines,
  currentData,
  measuredOutput,
  jsonFigurePaths,
  onClose,
  onSaved,
}: SpectroscopyCorrectionEditorProps) {
  const fieldId = useId();
  const [confirming, setConfirming] = useState(false);
  const [reviewed, setReviewed] = useState<CorrectionFormOutput>({});
  const [picking, setPicking] = useState(false);
  const [pendingPoint, setPendingPoint] = useState<PickedPoint | null>(null);
  const [selectedPoint, setSelectedPoint] = useState<PickedPoint | null>(null);
  const mutation = useUpdateCalibrationParameters();

  const schema = useMemo(() => spectroscopyCorrectionSchema(names, baselines), [names, baselines]);
  const {
    register,
    control,
    handleSubmit,
    setValue,
    formState: { errors, isValid },
  } = useForm<CorrectionFormInput, unknown, CorrectionFormOutput>({
    resolver: zodResolver(schema),
    mode: "onChange",
    defaultValues: Object.fromEntries(names.map((name) => [name, formatValue(baselines[name])])),
  });
  const values = useWatch({ control }) as Partial<CorrectionFormInput>;
  const changedNames = names.filter((name) =>
    isCorrectionChanged(values[name], baselines[name] ?? null),
  );

  /** Holds the validated values and opens the confirmation step. */
  const review = (parameters: CorrectionFormOutput) => {
    setReviewed(parameters);
    setConfirming(true);
  };

  /** Sends the reviewed values as a linked manual parameter edit. */
  const save = () => {
    mutation.mutate(
      {
        data: {
          chip_id: chipId,
          qid,
          source_task_id: taskId,
          correction_point: selectedPoint ?? undefined,
          parameters: Object.fromEntries(
            Object.entries(reviewed).map(([name, value]) => [
              name,
              { value, unit: parameterUnit(measuredOutput(name), name) },
            ]),
          ),
        },
      },
      {
        onSuccess: (response) => {
          setConfirming(false);
          onSaved(response.data);
        },
      },
    );
  };

  /** Writes a value into the form and revalidates it. */
  const setCorrection = (name: string, value: string) => {
    setValue(name, value, { shouldDirty: true, shouldValidate: true });
  };

  /** Stages the clicked data point as the pending correction point. */
  const handlePlotClick = (event: PlotMouseEvent) => {
    const point = event.points?.[0];
    if (!point) return;
    const x = Number(point.x);
    const y = Number(point.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;

    setPendingPoint({ x, y });
  };

  /** Applies the pending point to the form and closes the picker. */
  const useSelectedPoint = () => {
    if (!pendingPoint) return;
    for (const [name, value] of Object.entries(correctionValuesFromPoint(taskName, pendingPoint))) {
      if (names.includes(name)) setCorrection(name, value);
    }
    setSelectedPoint(pendingPoint);
    setPendingPoint(null);
    setPicking(false);
  };

  /** Opens the plot picker with the current selection staged. */
  const openPicker = () => {
    setPendingPoint(selectedPoint);
    setPicking(true);
  };

  return (
    <div className="overflow-hidden rounded-[var(--radius-box)] border border-base-300 bg-base-100 shadow-sm">
      <div className="flex flex-col gap-3 border-b border-base-300 bg-base-200/50 p-4 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Pencil size={16} className="text-warning" />
            <h3 className="text-sm font-medium">Manual spectroscopy correction</h3>
          </div>
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-base-content/60">
            Enter the operating values read from the stored figure. The measured frequency and the
            original result are preserved; a linked ManualParameterEdit result updates only the
            fields changed here.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {jsonFigurePaths.length > 0 && (
            <button className="btn btn-sm btn-outline" onClick={openPicker}>
              <Crosshair data-icon="inline-start" />
              Pick x/y from plot
            </button>
          )}
          <button
            className="btn btn-sm btn-ghost btn-square"
            aria-label="Close manual correction"
            onClick={onClose}
          >
            <X size={16} />
          </button>
        </div>
      </div>
      <form className="p-4" noValidate onSubmit={handleSubmit(review)}>
        {selectedPoint && jsonFigurePaths[0] && (
          <div className="mb-3 flex flex-col gap-2 rounded-lg border border-primary/25 bg-primary/5 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2 text-xs">
              <Crosshair size={14} className="shrink-0 text-primary" />
              <span className="text-base-content/60">Selected point</span>
              <span className="font-mono font-medium">
                x={formatCoordinate(selectedPoint.x)}, y={formatCoordinate(selectedPoint.y)}
              </span>
            </div>
            <button type="button" className="btn btn-xs btn-ghost" onClick={openPicker}>
              View corrected figure
            </button>
          </div>
        )}
        <div className="overflow-x-auto rounded-lg border border-base-300">
          <table className="table table-sm min-w-[720px]">
            <thead>
              <tr>
                <th>Parameter</th>
                <th>Measured</th>
                <th>Current DB</th>
                <th>Corrected</th>
                <th>Unit</th>
              </tr>
            </thead>
            <tbody>
              {names.map((name) => {
                const measured = parameterValue(measuredOutput(name));
                const current = parameterValue(currentData[name]);
                const baseline = baselines[name] ?? null;
                const changed = changedNames.includes(name);
                const error = errors[name]?.message;
                const inputId = `${fieldId}-${name}`;
                return (
                  <tr key={name} className={changed ? "bg-warning/10" : ""}>
                    <td className="font-mono">{name}</td>
                    <td className="font-mono">{formatValue(measured) || "-"}</td>
                    <td className="font-mono">{formatValue(current) || "-"}</td>
                    <td>
                      <div className="flex items-center gap-1">
                        <input
                          id={inputId}
                          aria-label={`Correct ${name}`}
                          aria-invalid={Boolean(error)}
                          aria-describedby={error ? `${inputId}-error` : undefined}
                          className={`input input-bordered input-sm w-40 font-mono ${error ? "input-error" : changed ? "input-warning" : ""}`}
                          inputMode="decimal"
                          placeholder="Enter a value"
                          {...register(name)}
                        />
                        {changed && (
                          <button
                            type="button"
                            className="btn btn-ghost btn-xs btn-square"
                            title="Reset"
                            onClick={() => setCorrection(name, formatValue(baseline))}
                          >
                            <RotateCcw className="h-3 w-3" />
                          </button>
                        )}
                      </div>
                      {error && (
                        <p id={`${inputId}-error`} className="mt-1 text-xs text-error">
                          {error}
                        </p>
                      )}
                    </td>
                    <td>{parameterUnit(measuredOutput(name), name)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {mutation.isError && (
          <div className="alert alert-error mt-3 text-sm">
            Correction failed: {getApiErrorMessage(mutation.error, "Unknown error")}
          </div>
        )}
        <div className="mt-4 flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-base-content/60">
            {changedNames.length === 0
              ? NO_CHANGE_ERROR
              : `${changedNames.length} ${changedNames.length === 1 ? "value" : "values"} will be updated.`}
          </p>
          <button
            type="submit"
            className="btn btn-warning btn-sm"
            disabled={!isValid || mutation.isPending}
          >
            Review changes
          </button>
        </div>
      </form>

      <Dialog open={confirming} onOpenChange={(open) => !mutation.isPending && setConfirming(open)}>
        <DialogContent className="max-w-lg overflow-hidden p-0">
          <div className="flex items-start gap-3 border-b border-base-300 p-5">
            <div className="rounded-full bg-warning/15 p-2 text-warning">
              <AlertTriangle size={20} />
            </div>
            <div>
              <DialogTitle>Update calibration values?</DialogTitle>
              <DialogDescription className="mt-1 text-sm leading-relaxed text-base-content/60">
                A linked ManualParameterEdit will be created. The original Task Result and figure
                remain unchanged.
              </DialogDescription>
            </div>
          </div>
          <div className="p-5">
            <div className="rounded-lg border border-base-300 bg-base-200/40">
              <ul className="divide-y divide-base-300 text-sm">
                {Object.entries(reviewed).map(([name, value]) => (
                  <li key={name} className="flex items-center justify-between gap-4 px-3 py-2.5">
                    <span className="min-w-0 truncate font-mono text-xs">{name}</span>
                    <span className="shrink-0 font-mono text-xs font-medium">
                      {value} {parameterUnit(measuredOutput(name), name)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
            <p className="mt-3 break-all text-xs text-base-content/50">Source: {taskId}</p>
          </div>
          <div className="flex justify-end gap-2 border-t border-base-300 bg-base-200/40 px-5 py-4">
            <button
              className="btn btn-sm btn-ghost"
              disabled={mutation.isPending}
              onClick={() => setConfirming(false)}
            >
              Cancel
            </button>
            <button className="btn btn-sm btn-warning" disabled={mutation.isPending} onClick={save}>
              {mutation.isPending ? (
                <span className="loading loading-spinner loading-sm" />
              ) : (
                "Update DB"
              )}
            </button>
          </div>
        </DialogContent>
      </Dialog>

      <Dialog
        open={picking}
        onOpenChange={(open) => {
          setPicking(open);
          if (!open) setPendingPoint(null);
        }}
      >
        <DialogContent className="max-sm:top-auto max-sm:bottom-0 max-sm:translate-y-0 max-sm:rounded-b-none flex h-[88vh] w-full max-w-6xl flex-col overflow-hidden p-0">
          <div className="flex items-start justify-between gap-4 border-b border-base-300 px-5 py-4">
            <div>
              <DialogTitle>Pick frequency and power</DialogTitle>
              <DialogDescription className="mt-1 text-sm text-base-content/60">
                Click one data point to use its x and y coordinates. Plotly zoom and pan remain
                available.
              </DialogDescription>
            </div>
            <button
              className="btn btn-sm btn-ghost btn-square shrink-0"
              aria-label="Close plot picker"
              onClick={() => setPicking(false)}
            >
              <X size={18} />
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-auto bg-base-200 p-3 sm:p-5">
            {jsonFigurePaths[0] && (
              <div className="mx-auto w-fit max-w-full overflow-auto rounded-[var(--radius-box)] border border-base-300 bg-base-100 p-3 shadow-sm">
                <PlotlyRenderer
                  fullPath={`/api/executions/figure?path=${encodeURIComponent(jsonFigurePaths[0])}`}
                  onClick={handlePlotClick}
                  highlightPoint={
                    pendingPoint
                      ? { ...pendingPoint, label: "Manual correction" }
                      : selectedPoint
                        ? { ...selectedPoint, label: "Manual correction" }
                        : null
                  }
                />
              </div>
            )}
          </div>
          <div className="flex flex-col gap-3 border-t border-base-300 bg-base-100 px-5 py-3 sm:flex-row sm:items-center sm:justify-between">
            <p className="text-xs text-base-content/60">
              {pendingPoint
                ? `Selected x=${formatCoordinate(pendingPoint.x)}, y=${formatCoordinate(pendingPoint.y)}`
                : "Click a data point to preview the correction marker."}
            </p>
            <div className="flex justify-end gap-2">
              <button
                className="btn btn-sm btn-ghost"
                onClick={() => {
                  setPendingPoint(null);
                  setPicking(false);
                }}
              >
                Cancel
              </button>
              <button
                className="btn btn-sm btn-primary"
                disabled={!pendingPoint}
                onClick={useSelectedPoint}
              >
                Use selected point
              </button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}

/** Operational parameter names an operator may correct from a spectroscopy result. */
export function spectroscopyCorrectionParameterNames(taskName: string): string[] {
  return Object.keys(CORRECTION_PARAMETERS[taskName] ?? {});
}

/** Source output that holds the measured value shown next to a correction field. */
export function sourceOutputName(taskName: string, parameterName: string): string {
  return CORRECTION_PARAMETERS[taskName]?.[parameterName] ?? parameterName;
}

/** Corrected operating values derived from a point picked on the spectroscopy figure. */
export function correctionValuesFromPoint(
  taskName: string,
  point: PickedPoint,
): Record<string, string> {
  const { x, y } = point;
  if (taskName === "CheckResonatorSpectroscopy") {
    return {
      readout_frequency: String(x),
      readout_amplitude: String(10 ** (y / 20)),
    };
  }
  if (taskName === "CheckQubitSpectroscopy") {
    return {
      control_frequency: String(x),
      coarse_control_amplitude: String(
        Math.min(10 ** ((y + COARSE_CONTROL_AMPLITUDE_HEADROOM_DB) / 20), 1),
      ),
    };
  }
  return {};
}

/**
 * Zod schema for the correction form. Every changed value must be a finite number, at least
 * one value must change, and the output holds only the changed values as numbers.
 */
export function spectroscopyCorrectionSchema(
  names: string[],
  baselines: Record<string, number | null>,
): z.ZodType<CorrectionFormOutput, CorrectionFormInput> {
  const changedNames = (values: CorrectionFormInput) =>
    names.filter((name) => isCorrectionChanged(values[name], baselines[name] ?? null));
  return z
    .object(Object.fromEntries(names.map((name) => [name, z.string()])))
    .superRefine((values, ctx) => {
      const changed = changedNames(values);
      for (const name of changed) {
        if (parseFinite(values[name]) === null) {
          ctx.addIssue({ code: "custom", path: [name], message: INVALID_NUMBER_ERROR });
        }
      }
      if (changed.length === 0) {
        ctx.addIssue({ code: "custom", path: [], message: NO_CHANGE_ERROR });
      }
    })
    .transform((values) =>
      Object.fromEntries(
        changedNames(values).map((name) => [name, parseFinite(values[name]) as number]),
      ),
    );
}

/** Whether a field differs from its baseline; any non-empty value that is not a number does. */
function isCorrectionChanged(value: string | undefined, baseline: number | null): boolean {
  if (!value?.trim()) return baseline !== null;
  const parsed = parseFinite(value);
  return parsed === null || parsed !== baseline;
}

function parameterValue(raw: unknown): number | null {
  const value =
    typeof raw === "object" && raw !== null && "value" in raw
      ? (raw as { value: unknown }).value
      : raw;
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function parameterUnit(raw: unknown, name: string): string {
  if (
    typeof raw === "object" &&
    raw !== null &&
    "unit" in raw &&
    typeof (raw as { unit: unknown }).unit === "string"
  )
    return (raw as { unit: string }).unit;
  return PARAMETER_UNITS[name] ?? "";
}

function formatValue(value: number | null): string {
  return value === null ? "" : String(value);
}
function formatCoordinate(value: number): string {
  return Number(value.toPrecision(8)).toString();
}
function parseFinite(value: string | undefined): number | null {
  const parsed = Number(value);
  return value?.trim() && Number.isFinite(parsed) ? parsed : null;
}
