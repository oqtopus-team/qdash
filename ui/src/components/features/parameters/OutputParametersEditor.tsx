"use client";

import { useState } from "react";

import { useQueryClient } from "@tanstack/react-query";
import { Pencil } from "lucide-react";

import { useUpdateCalibrationParameters } from "@/client/calibration/calibration";
import {
  getGetChipCouplingQueryKey,
  getGetChipQubitQueryKey,
  useGetChipCoupling,
  useGetChipQubit,
} from "@/client/chip/chip";
import { ParametersTable } from "@/components/features/metrics/ParametersTable";
import {
  CommitParametersModal,
  type CommitParameterRow,
} from "@/components/features/parameters/CommitParametersModal";
import {
  formatOutputValue,
  OutputParameterTable,
  parseFloatOrNull,
  qidLabel,
  type OutputParameterEditRow,
} from "@/components/features/parameters/OutputParameterTable";

interface OutputParametersEditorProps {
  chipId: string;
  /** Qubit id ("4") or coupling id ("4-5"). */
  qid: string;
  /** Task result whose snapshot values are corrected. */
  taskId: string;
  /** Raw output_parameters of the task result, as stored. */
  outputParameters: Record<string, unknown>;
}

interface StoredParameter {
  value: number;
  unit?: string;
  description?: string;
  derivedFrom?: string;
}

/**
 * Manual correction of a task result's output parameters, for a qubit or a coupling. Values
 * are written to the calibration DB with a task-result history row and provenance records.
 */
export function OutputParametersEditor({
  chipId,
  qid,
  taskId,
  outputParameters,
}: OutputParametersEditorProps) {
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const queryClient = useQueryClient();
  // Same endpoint the metrics and task-history modals use, so every manual edit is recorded
  // the same way. source_task_id ties this one back to the experiment it was read from.
  const mutation = useUpdateCalibrationParameters();
  // Current is the calibration DB value being replaced, not this task result's own value.
  // Qubit and coupling calibration data live in different collections, hence two queries.
  const isCoupling = qid.includes("-");
  const { data: qubitResponse } = useGetChipQubit(chipId, qid, {
    query: { enabled: !isCoupling },
  });
  const { data: couplingResponse } = useGetChipCoupling(chipId, qid, {
    query: { enabled: isCoupling },
  });
  const calibrationValues = numericValues(
    (isCoupling ? couplingResponse?.data?.data : qubitResponse?.data?.data) ?? {},
  );

  const snapshot = numericParameters(outputParameters);
  const editable = snapshot.filter(([, parameter]) => !parameter.derivedFrom);

  const rows: OutputParameterEditRow[] = snapshot.map(([name, parameter]) => {
    const edit = edits[name];
    const currentValue = calibrationValues[name] ?? null;
    // New starts from the DB value being edited, so Delta reads as what this update changes.
    // Parameters absent from the DB fall back to the snapshot. Revert returns to this baseline.
    const baseline = currentValue ?? parameter.value;
    return {
      qid: "",
      name,
      unit: parameter.unit,
      snapshotValue: parameter.value,
      currentValue,
      analyzedValue: baseline,
      derivedFrom: parameter.derivedFrom,
      edited: edit !== undefined,
      value: edit ?? formatOutputValue(baseline),
    };
  });

  const commitRows: CommitParameterRow[] = rows
    .filter((row) => row.edited)
    .map((row) => ({ ...row, value: parseFloatOrNull(row.value) }));

  const canUpdate = commitRows.length > 0 && commitRows.every((row) => row.value !== null);

  const handleChange = (_qid: string, name: string, value: string) => {
    setEdits((current) => ({ ...current, [name]: value }));
  };

  const handleReset = (_qid: string, name: string) => {
    setEdits((current) => {
      if (!(name in current)) return current;
      const { [name]: _removed, ...rest } = current;
      return rest;
    });
  };

  const handleConfirm = () => {
    if (!canUpdate) return;
    setIsConfirmOpen(false);
    mutation.mutate(
      {
        data: {
          chip_id: chipId,
          qid,
          source_task_id: taskId,
          parameters: Object.fromEntries(
            commitRows.map((row) => [
              row.name,
              { value: row.value as number, unit: row.unit ?? "" },
            ]),
          ),
        },
      },
      {
        onSuccess: () => {
          setEdits({});
          void queryClient.invalidateQueries({
            queryKey: isCoupling
              ? getGetChipCouplingQueryKey(chipId, qid)
              : getGetChipQubitQueryKey(chipId, qid),
          });
          void queryClient.invalidateQueries({
            queryKey: [`/calibrations/manual-edits/${qid}`],
          });
        },
      },
    );
  };

  // Non-numeric outputs cannot be calibration values, but they still deserve to be shown.
  if (snapshot.length === 0) {
    return <ParametersTable title="Output Parameters" parameters={outputParameters} />;
  }

  return (
    <>
      <OutputParameterTable
        title="Output Parameters"
        description={
          editable.length > 0
            ? "Snapshot is what this experiment produced, Current is the calibration DB value now, and New starts from Current so Delta shows exactly what this update changes. Only rows you edit are written, as a task result linked to this one."
            : "Every value here is derived from another parameter and cannot be corrected directly."
        }
        rows={rows}
        showQubit={false}
        onChange={editable.length > 0 ? handleChange : undefined}
        onReset={handleReset}
        headerAction={
          <button
            type="button"
            className="btn btn-xs btn-warning gap-1"
            disabled={!canUpdate || mutation.isPending}
            onClick={() => setIsConfirmOpen(true)}
          >
            {mutation.isPending ? (
              <span className="loading loading-spinner loading-xs" />
            ) : (
              <Pencil size={12} />
            )}
            Update DB
          </button>
        }
      />

      {mutation.isError && (
        <div className="alert alert-error mt-2 text-sm">
          <span>Update failed: {(mutation.error as Error)?.message ?? "unknown"}</span>
        </div>
      )}
      {mutation.isSuccess && Object.keys(edits).length === 0 && (
        <div className="alert alert-success mt-2 text-sm">
          <span>Calibration DB updated.</span>
        </div>
      )}

      <CommitParametersModal
        isOpen={isConfirmOpen}
        isPending={mutation.isPending}
        rows={commitRows.map((row) => ({ ...row, qid }))}
        description={`These values replace the current calibration DB values for ${qidLabel(qid)}. ${commitRows.length} of ${snapshot.length} output parameters were edited.`}
        onClose={() => setIsConfirmOpen(false)}
        onConfirm={handleConfirm}
      />
    </>
  );
}

/** Flattens a calibration data map to plain finite numbers. */
function numericValues(calibrationData: Record<string, unknown>): Record<string, number> {
  const values: Record<string, number> = {};

  for (const [name, raw] of Object.entries(calibrationData)) {
    const value =
      typeof raw === "object" && raw !== null && "value" in raw
        ? (raw as { value: unknown }).value
        : raw;
    if (typeof value === "number" && Number.isFinite(value)) values[name] = value;
  }

  return values;
}

/** Keeps the numeric output parameters, which are the ones a calibration value can be. */
function numericParameters(outputParameters: Record<string, unknown>): [string, StoredParameter][] {
  const entries: [string, StoredParameter][] = [];

  for (const [name, raw] of Object.entries(outputParameters)) {
    const parameter = (
      typeof raw === "object" && raw !== null && "value" in raw ? raw : { value: raw }
    ) as {
      value: unknown;
      unit?: unknown;
      description?: unknown;
      derived_from?: unknown;
    };
    if (typeof parameter.value !== "number" || !Number.isFinite(parameter.value)) continue;
    entries.push([
      name,
      {
        value: parameter.value,
        unit: typeof parameter.unit === "string" ? parameter.unit : undefined,
        description: typeof parameter.description === "string" ? parameter.description : undefined,
        derivedFrom:
          typeof parameter.derived_from === "string" && parameter.derived_from
            ? parameter.derived_from
            : undefined,
      },
    ]);
  }

  return entries;
}
