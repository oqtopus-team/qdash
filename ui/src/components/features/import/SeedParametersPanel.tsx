"use client";

import { useState, useMemo, useCallback, useEffect } from "react";

import {
  Database,
  Check,
  AlertCircle,
  AlertTriangle,
  Loader2,
  ChevronDown,
  ChevronRight,
  RefreshCw,
  Search,
  Pencil,
  RotateCcw,
} from "lucide-react";

import { ChipSelector } from "@/components/selectors/ChipSelector";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";
import { useCompareSeedValues, useImportSeedParameters } from "@/client/calibration/calibration";
import { useListChipQubits, useListChips } from "@/client/chip/chip";
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

function formatComparisonValue(
  value: number | string | null | undefined,
  detailed: boolean,
): string {
  if (!detailed || typeof value !== "number") return formatValue(value);
  if (value === 0) return "0";
  if (Math.abs(value) < 0.0001 || Math.abs(value) > 10000) {
    return value.toExponential(9);
  }
  return value.toPrecision(10);
}

function valuesEqual(candidate: number | string, current: number | string): boolean {
  if (typeof candidate !== "number" || typeof current !== "number") return candidate === current;
  if (candidate === 0 || current === 0) return Math.abs(candidate - current) < 1e-9;
  return Math.abs(candidate - current) / Math.max(Math.abs(candidate), Math.abs(current)) < 1e-9;
}

interface QubitData {
  yaml_qid?: string;
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

interface QubitCalibrationData {
  qid: string;
  data?: Record<string, unknown>;
}

interface QubitListData {
  qubits: QubitCalibrationData[];
}

function calibrationValue(raw: unknown): { value: number | string; unit: string } | null {
  if (typeof raw === "number" || typeof raw === "string") return { value: raw, unit: "" };
  if (!raw || typeof raw !== "object") return null;
  const candidate = raw as { value?: unknown; unit?: unknown };
  if (typeof candidate.value !== "number" && typeof candidate.value !== "string") return null;
  return {
    value: candidate.value,
    unit: typeof candidate.unit === "string" ? candidate.unit : "",
  };
}

interface ImportEntry {
  parameterName: string;
  qid: string;
  value: number | string;
  yamlValue: number | string | null;
  currentValue: number | string | null;
  unit: string;
  edited: boolean;
}

function parseImportValue(raw: string): number | string | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const numeric = Number(trimmed);
  return Number.isNaN(numeric) ? trimmed : numeric;
}

export function SeedParametersPanel() {
  const [selectedChip, setSelectedChip] = useState<string>("");
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<"changes" | "all" | QubitData["status"]>("all");
  const [expandedParams, setExpandedParams] = useState<Set<string>>(new Set());
  const [selectedQubits, setSelectedQubits] = useState<Record<string, Set<string>>>({});
  const [editedValues, setEditedValues] = useState<Record<string, Record<string, string>>>({});
  const [editingCell, setEditingCell] = useState<string | null>(null);
  const [editingDraft, setEditingDraft] = useState("");
  const [confirmDialog, setConfirmDialog] = useState<{
    open: boolean;
    mode: "all" | "selected";
    entries: ImportEntry[];
  }>({ open: false, mode: "all", entries: [] });

  const { data: chipsResponse } = useListChips();

  useEffect(() => {
    if (selectedChip || !chipsResponse?.data?.chips?.length) return;
    const [defaultChip] = [...chipsResponse.data.chips].sort((a, b) => {
      const statusA = a.activity_status === "inactive" ? 1 : 0;
      const statusB = b.activity_status === "inactive" ? 1 : 0;
      if (statusA !== statusB) return statusA - statusB;
      const dateA = a.installed_at ? new Date(a.installed_at).getTime() : 0;
      const dateB = b.installed_at ? new Date(b.installed_at).getTime() : 0;
      return dateB - dateA;
    });
    setSelectedChip(defaultChip.chip_id);
  }, [chipsResponse, selectedChip]);

  // Fetch comparison data
  const {
    data: compareData,
    isLoading,
    isError,
    refetch,
    isRefetching,
  } = useCompareSeedValues(selectedChip, undefined, {
    query: {
      enabled: !!selectedChip,
      staleTime: 30000,
    },
  });

  const comparison = compareData?.data as CompareData | undefined;
  const {
    data: qubitsResponse,
    isLoading: isLoadingQubits,
    isError: isQubitListError,
    refetch: refetchQubits,
  } = useListChipQubits(
    selectedChip,
    { limit: 256 },
    {
      query: { enabled: !!selectedChip, staleTime: 30000 },
    },
  );
  const qubitList = qubitsResponse?.data as QubitListData | undefined;

  const data = useMemo<CompareData | undefined>(() => {
    if (!comparison && !qubitList) return undefined;
    const parameters: Record<string, ParameterData> = structuredClone(comparison?.parameters ?? {});

    qubitList?.qubits.forEach((qubit) => {
      Object.entries(qubit.data ?? {}).forEach(([parameterName, raw]) => {
        const current = calibrationValue(raw);
        if (!current) return;
        const parameter = (parameters[parameterName] ??= { unit: current.unit, qubits: {} });
        if (!parameter.unit && current.unit) parameter.unit = current.unit;
        const existing = parameter.qubits[qubit.qid];
        const status =
          existing?.yaml_value !== null && existing?.yaml_value !== undefined
            ? valuesEqual(existing.yaml_value, current.value)
              ? "same"
              : "different"
            : "same";
        parameter.qubits[qubit.qid] = {
          ...existing,
          yaml_value: existing?.yaml_value ?? null,
          qdash_value: current.value,
          status,
        };
      });
    });

    return { chip_id: selectedChip, parameters };
  }, [comparison, qubitList, selectedChip]);

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

  const setEditedValue = useCallback(
    (paramName: string, qid: string, raw: string, yamlValue: number | string | null) => {
      setEditedValues((previous) => {
        const parameterEdits = { ...(previous[paramName] ?? {}) };
        if (raw === String(yamlValue ?? "")) {
          delete parameterEdits[qid];
        } else {
          parameterEdits[qid] = raw;
        }
        return { ...previous, [paramName]: parameterEdits };
      });
      setSelectedQubits((previous) => ({
        ...previous,
        [paramName]: new Set(previous[paramName] ?? []).add(qid),
      }));
    },
    [],
  );

  const resetEditedValue = useCallback((paramName: string, qid: string, deselect: boolean) => {
    setEditedValues((previous) => {
      const parameterEdits = { ...(previous[paramName] ?? {}) };
      delete parameterEdits[qid];
      return { ...previous, [paramName]: parameterEdits };
    });
    if (deselect) {
      setSelectedQubits((previous) => {
        const parameterSelection = new Set(previous[paramName] ?? []);
        parameterSelection.delete(qid);
        return { ...previous, [paramName]: parameterSelection };
      });
    }
    setEditingCell(null);
  }, []);

  // Select all changed or manually edited values in a parameter.
  const selectAllInParam = useCallback(
    (paramName: string, paramData: ParameterData) => {
      const parameterEdits = editedValues[paramName] ?? {};
      const qidsToSelect = Object.entries(paramData.qubits)
        .filter(([qid, qubit]) => qubit.status !== "same" || parameterEdits[qid] !== undefined)
        .map(([qid]) => qid);
      setSelectedQubits((prev) => ({
        ...prev,
        [paramName]: new Set(qidsToSelect),
      }));
    },
    [editedValues],
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
    return Object.values(selectedQubits).reduce((sum, set) => sum + set.size, 0);
  }, [selectedQubits]);

  const editedCount = useMemo(
    () => Object.values(editedValues).reduce((sum, values) => sum + Object.keys(values).length, 0),
    [editedValues],
  );

  const visibleParameters = useMemo(() => {
    if (!data?.parameters) return [];
    const normalizedQuery = searchQuery.trim().toLowerCase();

    return Object.entries(data.parameters)
      .filter(([paramName]) => paramName.toLowerCase().includes(normalizedQuery))
      .map(([paramName, paramData]) => {
        const qubits = Object.fromEntries(
          Object.entries(paramData.qubits).filter(([qid, qubit]) => {
            if (statusFilter === "all") return true;
            if (statusFilter === "changes") {
              return qubit.status !== "same" || editedValues[paramName]?.[qid] !== undefined;
            }
            return qubit.status === statusFilter;
          }),
        );
        return [paramName, { ...paramData, qubits }] as const;
      })
      .filter(([, paramData]) => Object.keys(paramData.qubits).length > 0);
  }, [data, editedValues, searchQuery, statusFilter]);

  const handleChipSelect = useCallback((chipId: string) => {
    setSelectedChip(chipId);
    setExpandedParams(new Set());
    setSelectedQubits({});
    setEditedValues({});
    setEditingCell(null);
    setEditingDraft("");
    setSearchQuery("");
    setStatusFilter("all");
  }, []);

  const collectImportEntries = useCallback(
    (mode: "all" | "selected") => {
      const entries: ImportEntry[] = [];
      if (!data) return entries;
      Object.entries(data.parameters).forEach(([paramName, paramData]) => {
        Object.entries(paramData.qubits).forEach(([qid, qubitData]) => {
          const editedRaw = editedValues[paramName]?.[qid];
          const edited = editedRaw !== undefined;
          if (!edited && qubitData.status === "same") return;
          if (mode === "selected") {
            const paramSelected = selectedQubits[paramName];
            if (!paramSelected || !paramSelected.has(qid)) return;
          }
          const value = edited ? parseImportValue(editedRaw) : qubitData.yaml_value;
          if (value === null) return;
          entries.push({
            parameterName: paramName,
            qid,
            value,
            yamlValue: qubitData.yaml_value,
            currentValue: qubitData.qdash_value,
            unit: paramData.unit,
            edited,
          });
        });
      });
      return entries;
    },
    [data, editedValues, selectedQubits],
  );

  // Execute import (called after confirmation or directly if no overwrites)
  const executeImport = useCallback(
    (mode: "all" | "selected") => {
      if (!selectedChip) return;

      const entries = collectImportEntries(mode);
      if (entries.length === 0) return;

      // Build manual_data for import
      const manualData: Record<
        string,
        Record<string, { value: number | string; unit: string }>
      > = {};

      entries.forEach((entry) => {
        if (!manualData[entry.parameterName]) manualData[entry.parameterName] = {};
        manualData[entry.parameterName][entry.qid] = {
          value: entry.value,
          unit: entry.unit,
        };
      });

      importMutation.mutate(
        {
          data: {
            chip_id: selectedChip,
            source: "manual" as SeedImportSource,
            manual_data: manualData,
          },
        },
        {
          onSuccess: async () => {
            // Clear selections and refetch
            setSelectedQubits({});
            setEditedValues({});
            setEditingCell(null);
            setEditingDraft("");
            setConfirmDialog({ open: false, mode: "all", entries: [] });
            await Promise.all([refetch(), refetchQubits()]);
          },
        },
      );
    },
    [selectedChip, collectImportEntries, importMutation, refetch, refetchQubits],
  );

  // Request import (shows confirmation if there are overwrites)
  const requestImport = useCallback(
    (mode: "all" | "selected") => {
      const entries = collectImportEntries(mode);
      if (entries.length > 0) setConfirmDialog({ open: true, mode, entries });
    },
    [collectImportEntries],
  );

  // Handle confirmation dialog actions
  const handleConfirmImport = useCallback(() => {
    executeImport(confirmDialog.mode);
  }, [confirmDialog.mode, executeImport]);

  const handleCancelImport = useCallback(() => {
    setConfirmDialog({ open: false, mode: "all", entries: [] });
  }, []);

  return (
    <div className="card bg-base-200">
      <div className="card-body p-4 sm:p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="card-title text-base sm:text-lg gap-2">
            <Database className="h-4 w-4 sm:h-5 sm:w-5" />
            Current calibration values
          </h3>
          {selectedChip && (
            <button
              className="btn btn-sm btn-ghost gap-1"
              onClick={() => refetch()}
              disabled={isRefetching}
            >
              <RefreshCw className={`h-4 w-4 ${isRefetching ? "animate-spin" : ""}`} />
              Refresh
            </button>
          )}
        </div>

        <p className="text-sm text-base-content/70 mb-4">
          Latest values stored in QDash. YAML values appear as proposed updates when available.
        </p>

        {/* Chip Selection */}
        <div className="form-control mb-4">
          <label className="label">
            <span className="label-text">Target Chip</span>
          </label>
          <ChipSelector selectedChip={selectedChip} onChipSelect={handleChipSelect} />
        </div>

        {/* Loading State */}
        {(isLoading || isLoadingQubits) && selectedChip && (
          <div className="flex justify-center py-8">
            <span className="loading loading-spinner loading-md"></span>
          </div>
        )}

        {(isError || isQubitListError) && selectedChip && (
          <div className="alert alert-error mb-4" role="alert">
            <AlertCircle className="h-5 w-5" />
            <span className="flex-1">Failed to load calibration values for {selectedChip}.</span>
            <button type="button" className="btn btn-sm btn-ghost" onClick={() => refetch()}>
              Retry
            </button>
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
            {editedCount > 0 && (
              <div className="badge badge-info gap-1">
                <Pencil className="h-3 w-3" />
                <span className="font-medium">{editedCount}</span> Edited
              </div>
            )}
          </div>
        )}

        {/* Import Success */}
        {importMutation.isSuccess && (
          <div className="alert alert-success mb-4">
            <Check className="h-5 w-5" />
            <span>
              Applied {importMutation.data?.data?.imported_count} calibration values successfully
            </span>
          </div>
        )}

        {/* Import Error */}
        {importMutation.isError && (
          <div className="alert alert-error mb-4">
            <AlertCircle className="h-5 w-5" />
            <span>Update failed: {String(importMutation.error)}</span>
          </div>
        )}

        {data && counts.total > 0 && (
          <div className="flex flex-col gap-3 rounded-xl border border-base-300 bg-base-100 p-3 sm:flex-row sm:items-center sm:justify-between">
            <label className="input input-sm input-bordered flex w-full items-center gap-2 sm:max-w-xs">
              <Search className="h-4 w-4 text-base-content/40" aria-hidden="true" />
              <input
                type="search"
                className="grow"
                value={searchQuery}
                onChange={(event) => setSearchQuery(event.target.value)}
                placeholder="Find a parameter"
                aria-label="Find a parameter"
              />
            </label>
            <div className="flex items-center gap-2">
              <label htmlFor="seed-status-filter" className="text-xs text-base-content/60">
                Show
              </label>
              <select
                id="seed-status-filter"
                className="select select-sm select-bordered"
                value={statusFilter}
                onChange={(event) =>
                  setStatusFilter(event.target.value as "changes" | "all" | QubitData["status"])
                }
              >
                <option value="changes">Changes only</option>
                <option value="new">New only</option>
                <option value="different">Different only</option>
                <option value="same">Same only</option>
                <option value="all">All values</option>
              </select>
            </div>
          </div>
        )}

        {data && (counts.new > 0 || counts.different > 0 || editedCount > 0) && (
          <div className="sticky top-16 z-20 flex items-center justify-between gap-3 rounded-xl border border-base-300 bg-base-100/95 p-3 shadow-sm backdrop-blur">
            <div className="text-xs text-base-content/60">
              <span className="font-semibold text-base-content">
                {visibleParameters.length} parameters shown
              </span>
              {selectedCount > 0 && <span> · {selectedCount} values selected</span>}
              {editedCount > 0 && <span> · {editedCount} manually edited</span>}
            </div>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button type="button" className="btn btn-primary btn-sm gap-2">
                  {importMutation.isPending ? (
                    <>
                      <Loader2 className="h-4 w-4 animate-spin" />
                      Importing...
                    </>
                  ) : (
                    <>
                      <Database className="h-4 w-4" />
                      Import from YAML
                      <ChevronDown className="h-4 w-4" />
                    </>
                  )}
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-64">
                <DropdownMenuItem
                  onSelect={() => requestImport("all")}
                  disabled={importMutation.isPending}
                >
                  Review all YAML changes ({collectImportEntries("all").length})
                </DropdownMenuItem>
                <DropdownMenuItem
                  onSelect={() => requestImport("selected")}
                  disabled={importMutation.isPending || selectedCount === 0}
                >
                  Review selected changes ({selectedCount})
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        )}

        {/* Parameters List */}
        {data && Object.keys(data.parameters).length > 0 && visibleParameters.length > 0 && (
          <div className="space-y-2">
            {visibleParameters.map(([paramName, paramData]) => {
              const isExpanded = expandedParams.has(paramName);
              const paramSelected = selectedQubits[paramName] || new Set();
              const paramCounts = Object.values(paramData.qubits).reduce(
                (result, qubit) => ({ ...result, [qubit.status]: result[qubit.status] + 1 }),
                { new: 0, different: 0, same: 0 },
              );
              const parameterEdits = editedValues[paramName] ?? {};
              const selectableCount = Object.entries(paramData.qubits).filter(
                ([qid, qubit]) => qubit.status !== "same" || parameterEdits[qid] !== undefined,
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
                        <span className="text-xs text-base-content/50">({paramData.unit})</span>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      {paramCounts.new > 0 && (
                        <span className="badge badge-success badge-sm">{paramCounts.new} new</span>
                      )}
                      {paramCounts.different > 0 && (
                        <span className="badge badge-warning badge-sm">
                          {paramCounts.different} different
                        </span>
                      )}
                      {paramSelected.size > 0 && (
                        <span className="badge badge-primary badge-sm">
                          {paramSelected.size} selected
                        </span>
                      )}
                      {Object.keys(parameterEdits).length > 0 && (
                        <span className="badge badge-info badge-sm">
                          {Object.keys(parameterEdits).length} edited
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
                          disabled={selectableCount === 0}
                        >
                          Select All ({selectableCount})
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
                              <th>YAML</th>
                              <th>Current QDash</th>
                              <th>Proposed</th>
                              <th>Status</th>
                              <th className="w-12">
                                <span className="sr-only">Edit</span>
                              </th>
                            </tr>
                          </thead>
                          <tbody>
                            {Object.entries(paramData.qubits).map(([qid, qubitData]) => {
                              const cellKey = `${paramName}:${qid}`;
                              const editedRaw = parameterEdits[qid];
                              const isEdited = editedRaw !== undefined;
                              const isEditing = editingCell === cellKey;
                              const parsedValue = isEdited ? parseImportValue(editedRaw) : null;
                              const inputValue = editedRaw ?? String(qubitData.yaml_value ?? "");
                              const isInvalid =
                                isEditing && parseImportValue(editingDraft) === null;
                              const selectable = qubitData.status !== "same" || isEdited;

                              return (
                                <tr
                                  key={qid}
                                  className={
                                    isEdited
                                      ? "bg-info/5"
                                      : qubitData.status === "same"
                                        ? "opacity-60"
                                        : qubitData.status === "different"
                                          ? "bg-warning/5"
                                          : ""
                                  }
                                >
                                  <td>
                                    <input
                                      type="checkbox"
                                      className="checkbox checkbox-xs"
                                      aria-label={`Select ${paramName} for qubit ${qid}`}
                                      checked={paramSelected.has(qid)}
                                      disabled={!selectable}
                                      onChange={() => toggleQubit(paramName, qid)}
                                    />
                                  </td>
                                  <td>
                                    <span className="font-mono">{qid}</span>
                                    {qubitData.yaml_qid && qubitData.yaml_qid !== qid && (
                                      <span className="ml-2 text-xs text-base-content/50">
                                        YAML:{" "}
                                        <span className="font-mono">{qubitData.yaml_qid}</span>
                                      </span>
                                    )}
                                  </td>
                                  <td className="font-mono text-xs text-base-content/60">
                                    <span title={String(qubitData.yaml_value ?? "-")}>
                                      {formatComparisonValue(
                                        qubitData.yaml_value,
                                        qubitData.status === "different",
                                      )}
                                    </span>
                                  </td>
                                  <td className="font-mono text-xs font-medium">
                                    <span title={String(qubitData.qdash_value ?? "-")}>
                                      {formatComparisonValue(
                                        qubitData.qdash_value,
                                        qubitData.status === "different",
                                      )}
                                    </span>
                                  </td>
                                  <td className="min-w-48">
                                    {isEditing ? (
                                      <div className="flex items-center gap-1">
                                        <input
                                          autoFocus
                                          type="text"
                                          className={`input input-xs input-bordered w-36 font-mono ${isInvalid ? "input-error" : "input-info"}`}
                                          aria-label={`Proposed value for ${paramName}, qubit ${qid}`}
                                          value={editingDraft}
                                          onChange={(event) => setEditingDraft(event.target.value)}
                                          onKeyDown={(event) => {
                                            if (event.key === "Enter" && !isInvalid) {
                                              setEditedValue(
                                                paramName,
                                                qid,
                                                editingDraft,
                                                qubitData.yaml_value,
                                              );
                                              setEditingCell(null);
                                            }
                                            if (event.key === "Escape") setEditingCell(null);
                                          }}
                                        />
                                        <button
                                          type="button"
                                          className="btn btn-xs btn-primary"
                                          disabled={isInvalid}
                                          onClick={() => {
                                            setEditedValue(
                                              paramName,
                                              qid,
                                              editingDraft,
                                              qubitData.yaml_value,
                                            );
                                            setEditingCell(null);
                                          }}
                                        >
                                          Save
                                        </button>
                                        <button
                                          type="button"
                                          className="btn btn-xs btn-ghost"
                                          onClick={() => setEditingCell(null)}
                                        >
                                          Cancel
                                        </button>
                                      </div>
                                    ) : (
                                      <div className="flex items-center gap-2">
                                        <span
                                          className={`font-mono text-xs ${selectable ? "font-semibold text-success" : ""}`}
                                        >
                                          {formatValue(
                                            isEdited ? parsedValue : qubitData.yaml_value,
                                          )}
                                        </span>
                                        {isEdited && (
                                          <span className="badge badge-info badge-xs">Edited</span>
                                        )}
                                      </div>
                                    )}
                                    {isInvalid && (
                                      <p className="mt-1 text-xs text-error">Enter a value.</p>
                                    )}
                                  </td>
                                  <td>
                                    {qubitData.yaml_value === null && !isEdited ? (
                                      <span className="badge badge-ghost badge-xs">Current</span>
                                    ) : (
                                      <span
                                        className={`badge badge-xs ${STATUS_STYLES[qubitData.status]}`}
                                      >
                                        {STATUS_LABELS[qubitData.status]}
                                      </span>
                                    )}
                                  </td>
                                  <td>
                                    <div className="flex justify-end gap-1">
                                      {isEdited && (
                                        <button
                                          type="button"
                                          className="btn btn-xs btn-ghost btn-square"
                                          aria-label={`Reset ${paramName} for qubit ${qid} to YAML value`}
                                          title="Reset to YAML value"
                                          onClick={() =>
                                            resetEditedValue(
                                              paramName,
                                              qid,
                                              qubitData.status === "same",
                                            )
                                          }
                                        >
                                          <RotateCcw className="h-3.5 w-3.5" />
                                        </button>
                                      )}
                                      <button
                                        type="button"
                                        className="btn btn-xs btn-ghost btn-square"
                                        aria-label={`Edit ${paramName} for qubit ${qid}`}
                                        title="Edit import value"
                                        onClick={() => {
                                          setEditingDraft(inputValue);
                                          setEditingCell(cellKey);
                                        }}
                                      >
                                        <Pencil className="h-3.5 w-3.5" />
                                      </button>
                                    </div>
                                  </td>
                                </tr>
                              );
                            })}
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

        {data && Object.keys(data.parameters).length > 0 && visibleParameters.length === 0 && (
          <div className="rounded-xl border border-dashed border-base-300 py-10 text-center">
            <Search className="mx-auto mb-2 h-8 w-8 text-base-content/25" aria-hidden="true" />
            <p className="text-sm font-medium">No parameters match this view</p>
            <p className="mt-1 text-xs text-base-content/60">
              Try another search or status filter.
            </p>
          </div>
        )}

        {/* Empty State */}
        {data && Object.keys(data.parameters).length === 0 && (
          <div className="text-center py-8 text-base-content/60">
            <Database className="h-12 w-12 mx-auto mb-2 opacity-30" />
            <p>No calibration parameters found for this chip.</p>
          </div>
        )}

        {/* No Chip Selected */}
        {!selectedChip && (
          <div className="text-center py-8 text-base-content/60">
            <p>Select a chip to view its latest calibration values.</p>
          </div>
        )}

        {/* Overwrite Confirmation Dialog */}
        {confirmDialog.open && (
          <Dialog
            open
            onOpenChange={(open) => !open && !importMutation.isPending && handleCancelImport()}
          >
            <DialogContent>
              <div className="flex items-start gap-3">
                <AlertTriangle className="h-6 w-6 text-warning flex-shrink-0 mt-1" />
                <div className="min-w-0 flex-1">
                  <DialogTitle>Review calibration updates</DialogTitle>
                  <DialogDescription className="py-3">
                    Apply {confirmDialog.entries.length} value(s) to {selectedChip}.{" "}
                    <span className="font-semibold text-warning">
                      {
                        confirmDialog.entries.filter(
                          (entry) =>
                            entry.currentValue !== null && entry.currentValue !== undefined,
                        ).length
                      }{" "}
                      existing value(s)
                    </span>{" "}
                    will be overwritten.
                  </DialogDescription>
                  <div className="max-h-72 overflow-auto rounded-lg border border-base-300">
                    <table className="table table-xs">
                      <thead>
                        <tr>
                          <th>Parameter</th>
                          <th>Qubit</th>
                          <th>YAML</th>
                          <th>Current QDash</th>
                          <th>Proposed</th>
                        </tr>
                      </thead>
                      <tbody>
                        {confirmDialog.entries.map((entry) => (
                          <tr key={`${entry.parameterName}:${entry.qid}`}>
                            <td>
                              <span className="font-medium">{entry.parameterName}</span>
                              {entry.edited && (
                                <span className="badge badge-info badge-xs ml-2">Edited</span>
                              )}
                            </td>
                            <td className="font-mono">{entry.qid}</td>
                            <td className="font-mono text-base-content/60">
                              {formatValue(entry.yamlValue)}
                            </td>
                            <td className="font-mono text-base-content/60">
                              {formatValue(entry.currentValue)}
                            </td>
                            <td className="font-mono font-semibold text-success">
                              {formatValue(entry.value)} {entry.unit}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
              <div className="modal-action">
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={handleCancelImport}
                  disabled={importMutation.isPending}
                >
                  Cancel
                </button>
                <button
                  type="button"
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
                    `Apply ${confirmDialog.entries.length} values`
                  )}
                </button>
              </div>
            </DialogContent>
          </Dialog>
        )}
      </div>
    </div>
  );
}
