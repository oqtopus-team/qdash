"use client";

import { CalibrationGitHubSyncNotice } from "@/components/features/task-results/CalibrationGitHubSyncNotice";
import type { ManualParameterUpdateResponse } from "@/schemas";

import { useMemo, useState } from "react";

import { useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, Crosshair, Pencil, RotateCcw, X } from "lucide-react";
import type { PlotMouseEvent } from "plotly.js";

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

/** Manually correct spectroscopy outputs while retaining the source Task Result. */
export function SpectroscopyManualCorrection({
  chipId,
  qid,
  taskId,
  taskName,
  outputParameters,
  jsonFigurePaths,
}: SpectroscopyManualCorrectionProps) {
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [values, setValues] = useState<Record<string, string>>({});
  const [baselines, setBaselines] = useState<Record<string, number | null>>({});
  const [picking, setPicking] = useState(false);
  const [pendingPoint, setPendingPoint] = useState<PickedPoint | null>(null);
  const [selectedPoint, setSelectedPoint] = useState<PickedPoint | null>(null);
  const [createdTaskId, setCreatedTaskId] = useState<string | null>(null);
  const [githubResult, setGithubResult] = useState<ManualParameterUpdateResponse | null>(null);
  const queryClient = useQueryClient();
  const mutation = useUpdateCalibrationParameters();
  const { data: qubitResponse } = useGetChipQubit(chipId, qid);

  const names = useMemo(() => spectroscopyCorrectionParameterNames(taskName), [taskName]);
  const currentData = (qubitResponse?.data?.data ?? {}) as Record<string, unknown>;
  const measuredOutput = (name: string) => outputParameters[sourceOutputName(taskName, name)];

  const beginEditing = () => {
    const nextBaselines = Object.fromEntries(
      names.map((name) => [
        name,
        parameterValue(currentData[name]) ?? parameterValue(measuredOutput(name)),
      ]),
    );
    setBaselines(nextBaselines);
    setValues(Object.fromEntries(names.map((name) => [name, formatValue(nextBaselines[name])])));
    setEditing(true);
  };

  const changedNames = names.filter((name) => {
    return parseFinite(values[name]) !== baselines[name];
  });
  const valid =
    changedNames.length > 0 && changedNames.every((name) => parseFinite(values[name]) !== null);

  const save = () => {
    if (!valid) return;
    mutation.mutate(
      {
        data: {
          chip_id: chipId,
          qid,
          source_task_id: taskId,
          correction_point: selectedPoint ?? undefined,
          parameters: Object.fromEntries(
            changedNames.map((name) => [
              name,
              {
                value: parseFinite(values[name]),
                unit: parameterUnit(measuredOutput(name), name),
              },
            ]),
          ),
        },
      },
      {
        onSuccess: (response) => {
          setGithubResult(response.data);
          setConfirming(false);
          setEditing(false);
          setCreatedTaskId(response.data.task_id);
          void queryClient.invalidateQueries({ queryKey: getGetChipQubitQueryKey(chipId, qid) });
          void queryClient.invalidateQueries({ queryKey: getGetTaskResultQueryKey(taskId) });
        },
      },
    );
  };

  const handlePlotClick = (event: PlotMouseEvent) => {
    const point = event.points?.[0];
    if (!point) return;
    const x = Number(point.x);
    const y = Number(point.y);
    if (!Number.isFinite(x) || !Number.isFinite(y)) return;

    setPendingPoint({ x, y });
  };

  const useSelectedPoint = () => {
    if (!pendingPoint) return;
    const { x, y } = pendingPoint;
    setValues((old) => ({ ...old, ...correctionValuesFromPoint(taskName, { x, y }) }));
    setSelectedPoint(pendingPoint);
    setPendingPoint(null);
    setPicking(false);
  };

  const openPicker = () => {
    setPendingPoint(selectedPoint);
    setPicking(true);
  };

  if (!editing) {
    return (
      <div className="rounded-xl border border-base-300 bg-base-100 p-4 shadow-sm">
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
          <button className="btn btn-sm btn-outline shrink-0 gap-2" onClick={beginEditing}>
            <Pencil size={14} />
            Correct values
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-xl border border-base-300 bg-base-100 shadow-sm">
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
            <button className="btn btn-sm btn-outline gap-2" onClick={openPicker}>
              <Crosshair size={14} />
              Pick x/y from plot
            </button>
          )}
          <button
            className="btn btn-sm btn-ghost btn-square"
            aria-label="Close manual correction"
            onClick={() => setEditing(false)}
          >
            <X size={16} />
          </button>
        </div>
      </div>
      <div className="p-4">
        {selectedPoint && jsonFigurePaths[0] && (
          <div className="mb-3 flex flex-col gap-2 rounded-lg border border-primary/25 bg-primary/5 px-3 py-2.5 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-center gap-2 text-xs">
              <Crosshair size={14} className="shrink-0 text-primary" />
              <span className="text-base-content/60">Selected point</span>
              <span className="font-mono font-medium">
                x={formatCoordinate(selectedPoint.x)}, y={formatCoordinate(selectedPoint.y)}
              </span>
            </div>
            <button className="btn btn-xs btn-ghost" onClick={openPicker}>
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
                const baseline = baselines[name];
                const changed = parseFinite(values[name]) !== baseline;
                return (
                  <tr key={name} className={changed ? "bg-warning/10" : ""}>
                    <td className="font-mono">{name}</td>
                    <td className="font-mono">{formatValue(measured) || "-"}</td>
                    <td className="font-mono">{formatValue(current) || "-"}</td>
                    <td>
                      <div className="flex items-center gap-1">
                        <input
                          aria-label={`Correct ${name}`}
                          className={`input input-bordered input-sm w-40 font-mono ${parseFinite(values[name]) === null ? "input-error" : changed ? "input-warning" : ""}`}
                          inputMode="decimal"
                          placeholder="Enter a value"
                          value={values[name] ?? ""}
                          onChange={(event) =>
                            setValues((old) => ({ ...old, [name]: event.target.value }))
                          }
                        />
                        {changed && (
                          <button
                            className="btn btn-ghost btn-xs btn-square"
                            title="Reset"
                            onClick={() =>
                              setValues((old) => ({ ...old, [name]: formatValue(baseline) }))
                            }
                          >
                            <RotateCcw className="h-3 w-3" />
                          </button>
                        )}
                      </div>
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
              ? "Change one or more values to continue."
              : `${changedNames.length} ${changedNames.length === 1 ? "value" : "values"} will be updated.`}
          </p>
          <button
            className="btn btn-warning btn-sm"
            disabled={!valid || mutation.isPending}
            onClick={() => setConfirming(true)}
          >
            Review changes
          </button>
        </div>
      </div>

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
                {changedNames.map((name) => (
                  <li key={name} className="flex items-center justify-between gap-4 px-3 py-2.5">
                    <span className="min-w-0 truncate font-mono text-xs">{name}</span>
                    <span className="shrink-0 font-mono text-xs font-medium">
                      {values[name]} {parameterUnit(measuredOutput(name), name)}
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
              <div className="mx-auto w-fit max-w-full overflow-auto rounded-xl border border-base-300 bg-base-100 p-3 shadow-sm">
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
