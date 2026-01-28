"use client";

import { useState, useMemo, useCallback } from "react";

import {
  Database,
  Check,
  AlertCircle,
  AlertTriangle,
  Loader2,
  ChevronDown,
  ChevronRight,
  RefreshCw,
} from "lucide-react";

import { ChipSelector } from "@/components/selectors/ChipSelector";
import {
  useCompareSeedValues,
  useImportSeedParameters,
} from "@/client/calibration/calibration";
import type { SeedImportSource } from "@/schemas";

// Status badge colors
const STATUS_STYLES = {
  new: "badge-success",
  different: "badge-warning",
  same: "badge-ghost",
} as const;

const STATUS_LABELS = {
  new: "New",
  different: "Diff",
  same: "Same",
} as const;

// Format value for display
function formatValue(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "number") {
    if (value === 0) return "0";
    if (Math.abs(value) < 0.0001 || Math.abs(value) > 10000) {
      return value.toExponential(4);
    }
    return value.toPrecision(6);
  }
  return String(value);
}

interface QubitData {
  yaml_value: number | string | null;
  qdash_value: number | string | null;
  status: "new" | "same" | "different";
}

interface ParameterData {
  unit: string;
  qubits: Record<string, QubitData>;
}

interface CompareData {
  chip_id: string;
  parameters: Record<string, ParameterData>;
}

export function SeedParametersPanel() {
  const [selectedChip, setSelectedChip] = useState<string>("");
  const [expandedParams, setExpandedParams] = useState<Set<string>>(new Set());
  const [selectedQubits, setSelectedQubits] = useState<
    Record<string, Set<string>>
  >({});
  const [confirmDialog, setConfirmDialog] = useState<{
    open: boolean;
    mode: "all" | "selected";
    diffCount: number;
  }>({ open: false, mode: "all", diffCount: 0 });

  // Fetch comparison data
  const {
    data: compareData,
    isLoading,
    refetch,
    isRefetching,
  } = useCompareSeedValues(selectedChip, undefined, {
    query: {
      enabled: !!selectedChip,
      staleTime: 30000,
    },
  });

  const data = compareData?.data as CompareData | undefined;

  // Import mutation
  const importMutation = useImportSeedParameters();

  // Get counts for display
  const counts = useMemo(() => {
    if (!data?.parameters) return { new: 0, different: 0, same: 0, total: 0 };

    let newCount = 0;
    let diffCount = 0;
    let sameCount = 0;

    Object.values(data.parameters).forEach((param) => {
      Object.values(param.qubits).forEach((qubit) => {
        if (qubit.status === "new") newCount++;
        else if (qubit.status === "different") diffCount++;
        else sameCount++;
      });
    });

    return {
      new: newCount,
      different: diffCount,
      same: sameCount,
      total: newCount + diffCount + sameCount,
    };
  }, [data]);

  // Toggle parameter expansion
  const toggleParam = useCallback((paramName: string) => {
    setExpandedParams((prev) => {
      const next = new Set(prev);
      if (next.has(paramName)) {
        next.delete(paramName);
      } else {
        next.add(paramName);
      }
      return next;
    });
  }, []);

  // Toggle qubit selection
  const toggleQubit = useCallback((paramName: string, qid: string) => {
    setSelectedQubits((prev) => {
      const paramSet = new Set(prev[paramName] || []);
      if (paramSet.has(qid)) {
        paramSet.delete(qid);
      } else {
        paramSet.add(qid);
      }
      return { ...prev, [paramName]: paramSet };
    });
  }, []);

  // Select all non-same qubits in a parameter
  const selectAllInParam = useCallback(
    (paramName: string, paramData: ParameterData) => {
      const qidsToSelect = Object.entries(paramData.qubits)
        .filter(([, q]) => q.status !== "same")
        .map(([qid]) => qid);
      setSelectedQubits((prev) => ({
        ...prev,
        [paramName]: new Set(qidsToSelect),
      }));
    },
    [],
  );

  // Clear selection for a parameter
  const clearParamSelection = useCallback((paramName: string) => {
    setSelectedQubits((prev) => ({
      ...prev,
      [paramName]: new Set(),
    }));
  }, []);

  // Get total selected count
  const selectedCount = useMemo(() => {
    return Object.values(selectedQubits).reduce(
      (sum, set) => sum + set.size,
      0,
    );
  }, [selectedQubits]);

  // Count items that would be overwritten for a given mode
  const countOverwrites = useCallback(
    (mode: "all" | "selected") => {
      if (!data) return 0;
      let diffCount = 0;
      Object.entries(data.parameters).forEach(([paramName, paramData]) => {
        Object.entries(paramData.qubits).forEach(([qid, qubitData]) => {
          if (qubitData.status !== "different") return;
          if (mode === "selected") {
            const paramSelected = selectedQubits[paramName];
            if (!paramSelected || !paramSelected.has(qid)) return;
          }
          diffCount++;
        });
      });
      return diffCount;
    },
    [data, selectedQubits],
  );

  // Execute import (called after confirmation or directly if no overwrites)
  const executeImport = useCallback(
    (mode: "all" | "selected") => {
      if (!selectedChip || !data) return;

      // Build manual_data for import
      const manualData: Record<string, Record<string, number | string>> = {};

      Object.entries(data.parameters).forEach(([paramName, paramData]) => {
        Object.entries(paramData.qubits).forEach(([qid, qubitData]) => {
          // Skip if same status (no need to import)
          if (qubitData.status === "same") return;

          // For 'selected' mode, check if this qubit is selected
          if (mode === "selected") {
            const paramSelected = selectedQubits[paramName];
            if (!paramSelected || !paramSelected.has(qid)) return;
          }

          // Add to manual_data
          if (!manualData[paramName]) {
            manualData[paramName] = {};
          }
          if (qubitData.yaml_value !== null) {
            manualData[paramName][qid] = qubitData.yaml_value;
          }
        });
      });

      if (Object.keys(manualData).length === 0) {
        return;
      }

      importMutation.mutate(
        {
          data: {
            chip_id: selectedChip,
            source: "manual" as SeedImportSource,
            manual_data: manualData,
          },
        },
        {
          onSuccess: () => {
            // Clear selections and refetch
            setSelectedQubits({});
            setConfirmDialog({ open: false, mode: "all", diffCount: 0 });
            refetch();
          },
        },
      );
    },
    [selectedChip, data, selectedQubits, importMutation, refetch],
  );

  // Request import (shows confirmation if there are overwrites)
  const requestImport = useCallback(
    (mode: "all" | "selected") => {
      const diffCount = countOverwrites(mode);
      if (diffCount > 0) {
        // Show confirmation dialog
        setConfirmDialog({ open: true, mode, diffCount });
      } else {
        // No overwrites, proceed directly
        executeImport(mode);
      }
    },
    [countOverwrites, executeImport],
  );

  // Handle confirmation dialog actions
  const handleConfirmImport = useCallback(() => {
    executeImport(confirmDialog.mode);
  }, [confirmDialog.mode, executeImport]);

  const handleCancelImport = useCallback(() => {
    setConfirmDialog({ open: false, mode: "all", diffCount: 0 });
  }, []);

  return (
    <div className="card bg-base-200">
      <div className="card-body p-4 sm:p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="card-title text-base sm:text-lg gap-2">
            <Database className="h-4 w-4 sm:h-5 sm:w-5" />
            Seed Parameters
          </h3>
          {selectedChip && (
            <button
              className="btn btn-sm btn-ghost gap-1"
              onClick={() => refetch()}
              disabled={isRefetching}
            >
              <RefreshCw
                className={`h-4 w-4 ${isRefetching ? "animate-spin" : ""}`}
              />
              Refresh
            </button>
          )}
        </div>

        <p className="text-sm text-base-content/70 mb-4">
          Compare and import initial calibration parameters from qubex YAML
          files.
        </p>

        {/* Chip Selection */}
        <div className="form-control mb-4">
          <label className="label">
            <span className="label-text">Target Chip</span>
          </label>
          <ChipSelector
            selectedChip={selectedChip}
            onChipSelect={setSelectedChip}
          />
        </div>

        {/* Loading State */}
        {isLoading && selectedChip && (
          <div className="flex justify-center py-8">
            <span className="loading loading-spinner loading-md"></span>
          </div>
        )}

        {/* Summary Stats */}
        {data && counts.total > 0 && (
          <div className="flex gap-2 mb-4 flex-wrap">
            <div className="badge badge-success gap-1">
              <span className="font-medium">{counts.new}</span> New
            </div>
            <div className="badge badge-warning gap-1">
              <span className="font-medium">{counts.different}</span> Different
            </div>
            <div className="badge badge-ghost gap-1">
              <span className="font-medium">{counts.same}</span> Same
            </div>
          </div>
        )}

        {/* Import Success */}
        {importMutation.isSuccess && (
          <div className="alert alert-success mb-4">
            <Check className="h-5 w-5" />
            <span>
              Imported {importMutation.data?.data?.imported_count} parameters
              successfully
            </span>
          </div>
        )}

        {/* Import Error */}
        {importMutation.isError && (
          <div className="alert alert-error mb-4">
            <AlertCircle className="h-5 w-5" />
            <span>Import failed: {String(importMutation.error)}</span>
          </div>
        )}

        {/* Parameters List */}
        {data && Object.keys(data.parameters).length > 0 && (
          <div className="space-y-2">
            {Object.entries(data.parameters).map(([paramName, paramData]) => {
              const isExpanded = expandedParams.has(paramName);
              const paramSelected = selectedQubits[paramName] || new Set();
              const nonSameCount = Object.values(paramData.qubits).filter(
                (q) => q.status !== "same",
              ).length;

              return (
                <div key={paramName} className="border border-base-300 rounded">
                  {/* Parameter Header */}
                  <div
                    className="flex items-center justify-between p-2 bg-base-100 cursor-pointer hover:bg-base-200"
                    onClick={() => toggleParam(paramName)}
                  >
                    <div className="flex items-center gap-2">
                      {isExpanded ? (
                        <ChevronDown className="h-4 w-4" />
                      ) : (
                        <ChevronRight className="h-4 w-4" />
                      )}
                      <span className="font-medium">{paramName}</span>
                      {paramData.unit && (
                        <span className="text-xs text-base-content/50">
                          ({paramData.unit})
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {paramSelected.size > 0 && (
                        <span className="badge badge-primary badge-sm">
                          {paramSelected.size} selected
                        </span>
                      )}
                      <span className="text-xs text-base-content/60">
                        {Object.keys(paramData.qubits).length} qubits
                      </span>
                    </div>
                  </div>

                  {/* Qubit Table */}
                  {isExpanded && (
                    <div className="p-2 border-t border-base-300">
                      {/* Quick Actions */}
                      <div className="flex gap-2 mb-2">
                        <button
                          className="btn btn-xs btn-ghost"
                          onClick={(e) => {
                            e.stopPropagation();
                            selectAllInParam(paramName, paramData);
                          }}
                          disabled={nonSameCount === 0}
                        >
                          Select All ({nonSameCount})
                        </button>
                        <button
                          className="btn btn-xs btn-ghost"
                          onClick={(e) => {
                            e.stopPropagation();
                            clearParamSelection(paramName);
                          }}
                          disabled={paramSelected.size === 0}
                        >
                          Clear
                        </button>
                      </div>

                      <div className="overflow-x-auto">
                        <table className="table table-xs">
                          <thead>
                            <tr>
                              <th className="w-8"></th>
                              <th>Qubit</th>
                              <th>YAML Value</th>
                              <th>QDash Value</th>
                              <th>Status</th>
                            </tr>
                          </thead>
                          <tbody>
                            {Object.entries(paramData.qubits).map(
                              ([qid, qubitData]) => (
                                <tr
                                  key={qid}
                                  className={
                                    qubitData.status === "same"
                                      ? "opacity-50"
                                      : ""
                                  }
                                >
                                  <td>
                                    <input
                                      type="checkbox"
                                      className="checkbox checkbox-xs"
                                      checked={paramSelected.has(qid)}
                                      disabled={qubitData.status === "same"}
                                      onChange={() =>
                                        toggleQubit(paramName, qid)
                                      }
                                    />
                                  </td>
                                  <td className="font-mono">{qid}</td>
                                  <td className="font-mono text-xs">
                                    {formatValue(qubitData.yaml_value)}
                                  </td>
                                  <td className="font-mono text-xs">
                                    {formatValue(qubitData.qdash_value)}
                                  </td>
                                  <td>
                                    <span
                                      className={`badge badge-xs ${STATUS_STYLES[qubitData.status]}`}
                                    >
                                      {STATUS_LABELS[qubitData.status]}
                                    </span>
                                  </td>
                                </tr>
                              ),
                            )}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* Empty State */}
        {data && Object.keys(data.parameters).length === 0 && (
          <div className="text-center py-8 text-base-content/60">
            <Database className="h-12 w-12 mx-auto mb-2 opacity-30" />
            <p>No seed parameters found for this chip.</p>
          </div>
        )}

        {/* No Chip Selected */}
        {!selectedChip && (
          <div className="text-center py-8 text-base-content/60">
            <p>Select a chip to view seed parameters.</p>
          </div>
        )}

        {/* Import Actions */}
        {data && (counts.new > 0 || counts.different > 0) && (
          <div className="card-actions justify-end mt-4 pt-4 border-t border-base-300">
            <div className="dropdown dropdown-end">
              <div tabIndex={0} role="button" className="btn btn-primary gap-2">
                {importMutation.isPending ? (
                  <>
                    <Loader2 className="h-4 w-4 animate-spin" />
                    Importing...
                  </>
                ) : (
                  <>
                    <Database className="h-4 w-4" />
                    Import
                    <ChevronDown className="h-4 w-4" />
                  </>
                )}
              </div>
              <ul
                tabIndex={0}
                className="dropdown-content z-[1] menu p-2 shadow bg-base-100 rounded-box w-56"
              >
                <li>
                  <button
                    onClick={() => requestImport("all")}
                    disabled={importMutation.isPending}
                  >
                    Import All New/Different ({counts.new + counts.different})
                  </button>
                </li>
                <li>
                  <button
                    onClick={() => requestImport("selected")}
                    disabled={importMutation.isPending || selectedCount === 0}
                  >
                    Import Selected Only ({selectedCount})
                  </button>
                </li>
              </ul>
            </div>
          </div>
        )}

        {/* Overwrite Confirmation Dialog */}
        {confirmDialog.open && (
          <div className="modal modal-open">
            <div className="modal-box">
              <div className="flex items-start gap-3">
                <AlertTriangle className="h-6 w-6 text-warning flex-shrink-0 mt-1" />
                <div>
                  <h3 className="font-bold text-lg">Confirm Overwrite</h3>
                  <p className="py-4">
                    This will overwrite{" "}
                    <span className="font-bold text-warning">
                      {confirmDialog.diffCount}
                    </span>{" "}
                    existing calibration value(s) with YAML seed values.
                  </p>
                  <p className="text-sm text-base-content/70">
                    Existing measured values will be replaced. This action
                    cannot be undone.
                  </p>
                </div>
              </div>
              <div className="modal-action">
                <button
                  className="btn btn-ghost"
                  onClick={handleCancelImport}
                  disabled={importMutation.isPending}
                >
                  Cancel
                </button>
                <button
                  className="btn btn-warning"
                  onClick={handleConfirmImport}
                  disabled={importMutation.isPending}
                >
                  {importMutation.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Importing...
                    </>
                  ) : (
                    "Overwrite"
                  )}
                </button>
              </div>
            </div>
            <div className="modal-backdrop" onClick={handleCancelImport}></div>
          </div>
        )}
      </div>
    </div>
  );
}
