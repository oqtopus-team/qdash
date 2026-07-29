"use client";

import {
  formatOutputValue,
  formatSignedOutputValue,
  groupRowsByParameter,
  ParameterGroupLabel,
  qidLabel,
  type OutputParameterEditRow,
} from "@/components/features/parameters/OutputParameterTable";

export type CommitParameterRow = Omit<OutputParameterEditRow, "value"> & {
  value: number | null;
};

interface CommitParametersModalProps {
  isOpen: boolean;
  isPending: boolean;
  rows: CommitParameterRow[];
  /** Shown above the table; explain what the commit writes. */
  description?: string;
  onClose: () => void;
  onConfirm: () => void;
}

/** Last look at the values before they replace calibration DB entries. */
export function CommitParametersModal({
  isOpen,
  isPending,
  rows,
  description,
  onClose,
  onConfirm,
}: CommitParametersModalProps) {
  if (!isOpen) return null;

  const canUpdate = rows.length > 0 && rows.every((row) => row.value !== null);
  const groups = groupRowsByParameter(rows);
  const qubits = [...new Set(rows.map((row) => row.qid))];
  const showSnapshot = rows.some(
    (row) => row.snapshotValue !== undefined && row.snapshotValue !== null,
  );
  const columnCount = showSnapshot ? 5 : 4;

  return (
    <dialog className="modal modal-open">
      <div className="modal-box">
        <h3 className="font-bold text-lg">Confirm DB Update</h3>
        <p className="pt-4 text-sm text-base-content/70">
          {description ??
            "Review the calibration DB changes before committing. The commit value will replace the current value for each listed output parameter."}
        </p>
        {/* Say outright what gets written, so nothing outside this list is a surprise. */}
        <div className="py-3 text-sm">
          <span className="font-medium">
            Writing {rows.length} {rows.length === 1 ? "value" : "values"} on{" "}
            {qubits.length === 1 ? qidLabel(qubits[0]) : `${qubits.length} qubits`}:
          </span>
          <span className="ml-2 inline-flex flex-wrap gap-1 align-middle">
            {groups.map((group) => (
              <span key={group.name} className="badge badge-outline badge-sm font-mono">
                {group.name}
                {group.rows.length > 1 ? ` ×${group.rows.length}` : ""}
              </span>
            ))}
          </span>
          <div className="mt-1 text-xs text-base-content/60">
            Output parameters not listed here are left unchanged.
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="table table-zebra table-xs">
            <thead>
              <tr>
                <th>Qubit</th>
                {showSnapshot && (
                  <th title="Value this parameter had when the experiment ran">Snapshot</th>
                )}
                <th title="Calibration DB value now">Current</th>
                <th>Commit</th>
                <th>Delta</th>
              </tr>
            </thead>
            {groups.map((group) => (
              <tbody key={group.name}>
                <tr className="bg-base-200">
                  <th colSpan={columnCount} className="font-medium">
                    <ParameterGroupLabel group={group} />
                  </th>
                </tr>
                {group.rows.map((row) => (
                  <tr key={`${row.qid}-${row.name}`}>
                    <td className="font-mono">{qidLabel(row.qid)}</td>
                    {showSnapshot && (
                      <td className="font-mono text-base-content/70">
                        {row.snapshotValue !== null && row.snapshotValue !== undefined
                          ? formatOutputValue(row.snapshotValue)
                          : "-"}
                      </td>
                    )}
                    <td className="font-mono">
                      {row.currentValue !== null && row.currentValue !== undefined
                        ? formatOutputValue(row.currentValue)
                        : "-"}
                    </td>
                    <td className="font-mono">
                      {row.value !== null ? (
                        formatOutputValue(row.value)
                      ) : (
                        <span className="text-warning">Missing</span>
                      )}
                    </td>
                    <td className="font-mono">
                      {row.value !== null &&
                      row.currentValue !== null &&
                      row.currentValue !== undefined
                        ? formatSignedOutputValue(row.value - row.currentValue)
                        : "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            ))}
          </table>
        </div>
        {!canUpdate && (
          <div className="alert alert-warning mt-3 text-sm">
            Enter finite values for every output parameter before updating the DB.
          </div>
        )}
        <div className="modal-action">
          <button className="btn" onClick={onClose} disabled={isPending}>
            Cancel
          </button>
          <button
            className="btn btn-warning"
            onClick={onConfirm}
            disabled={isPending || !canUpdate}
          >
            {isPending ? <span className="loading loading-spinner loading-sm" /> : "Update DB"}
          </button>
        </div>
      </div>
      <form method="dialog" className="modal-backdrop">
        <button onClick={onClose}>close</button>
      </form>
    </dialog>
  );
}
