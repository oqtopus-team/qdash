"use client";

import { useMemo, useState } from "react";

import { useCompareExecutions, useGetRecentExecutions } from "@/client/provenance/provenance";
import { ParameterLineageDialog } from "@/components/features/provenance/ParameterLineageDialog";
import { QubitTile } from "@/components/ui/QubitTile";
import { formatParameterValue } from "@/lib/formatParameterValue";
import type { ProvenanceTarget } from "@/lib/provenanceTarget";
import type { ParameterDiffResponse } from "@/schemas";

/** How many recent runs to search for the one published just before this execution (API maximum). */
const EXECUTION_WINDOW = 50;
/** Targets listed when a parameter is expanded, before the list folds behind "Show all". */
const VISIBLE_TARGETS = 10;

type DiffKind = "changed" | "added" | "removed";

interface TargetChange {
  row: ParameterDiffResponse;
  kind: DiffKind;
  /** Absolute relative change, used for ordering; new and removed values sort first. */
  magnitude: number;
}

/** Every change to one parameter across the chip, so a 100-qubit run reads as ~20 rows. */
interface ParameterGroup {
  parameterName: string;
  targets: TargetChange[];
  changed: number;
  added: number;
  removed: number;
  /** The target with the largest relative change, if any value changed. */
  largest: TargetChange | null;
  medianPercent: number | null;
}

function changeText(change: TargetChange): string {
  if (change.kind === "added") return "new";
  if (change.kind === "removed") return "removed";
  const percent = change.row.delta_percent;
  if (percent === null || percent === undefined) return "-";
  return `${percent > 0 ? "+" : ""}${percent.toFixed(2)} %`;
}

function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

function groupByParameter(diff: {
  changed_parameters: ParameterDiffResponse[];
  added_parameters: ParameterDiffResponse[];
  removed_parameters: ParameterDiffResponse[];
}): ParameterGroup[] {
  const groups = new Map<string, ParameterGroup>();
  const add = (row: ParameterDiffResponse, kind: DiffKind) => {
    const group = groups.get(row.parameter_name) ?? {
      parameterName: row.parameter_name,
      targets: [],
      changed: 0,
      added: 0,
      removed: 0,
      largest: null,
      medianPercent: null,
    };
    const magnitude =
      kind === "changed" ? Math.abs(row.delta_percent ?? 0) : Number.POSITIVE_INFINITY;
    group.targets.push({ row, kind, magnitude });
    group[kind] += 1;
    groups.set(row.parameter_name, group);
  };
  diff.changed_parameters.forEach((row) => add(row, "changed"));
  diff.added_parameters.forEach((row) => add(row, "added"));
  diff.removed_parameters.forEach((row) => add(row, "removed"));

  for (const group of groups.values()) {
    group.targets.sort((a, b) => b.magnitude - a.magnitude);
    const changedTargets = group.targets.filter((target) => target.kind === "changed");
    group.largest = changedTargets[0] ?? null;
    group.medianPercent = median(changedTargets.map((target) => target.magnitude));
  }
  return [...groups.values()].sort(
    (a, b) =>
      (b.largest?.magnitude ?? (b.added + b.removed > 0 ? Number.POSITIVE_INFINITY : -1)) -
        (a.largest?.magnitude ?? (a.added + a.removed > 0 ? Number.POSITIVE_INFINITY : -1)) ||
      a.parameterName.localeCompare(b.parameterName),
  );
}

function countText(group: ParameterGroup): string {
  const parts = [];
  if (group.changed) parts.push(`${group.changed} changed`);
  if (group.added) parts.push(`${group.added} new`);
  if (group.removed) parts.push(`${group.removed} removed`);
  return parts.join(", ");
}

function ParameterGroupRow({
  group,
  onSelect,
}: {
  group: ParameterGroup;
  onSelect: (target: ProvenanceTarget) => void;
}) {
  const [showAll, setShowAll] = useState(false);
  const visible = showAll ? group.targets : group.targets.slice(0, VISIBLE_TARGETS);
  return (
    <details className="group rounded-lg border border-base-300">
      <summary className="flex cursor-pointer list-none flex-wrap items-center gap-x-4 gap-y-1 px-3 py-2 hover:bg-base-200">
        <span className="min-w-40 font-medium">{group.parameterName}</span>
        <span className="text-xs text-base-content/60">{countText(group)}</span>
        {group.largest && (
          <span className="ml-auto flex items-center gap-1.5 text-xs">
            <span className="text-base-content/50">largest</span>
            <QubitTile qid={group.largest.row.qid} />
            <span className="font-mono">{changeText(group.largest)}</span>
            {group.medianPercent !== null && group.changed > 1 && (
              <span className="text-base-content/50">
                , median {group.medianPercent.toFixed(2)} %
              </span>
            )}
          </span>
        )}
      </summary>
      <div className="overflow-x-auto border-t border-base-300">
        <table className="table table-xs">
          <thead>
            <tr>
              <th>Target</th>
              <th className="text-right">Before</th>
              <th className="text-right">After</th>
              <th className="text-right">Change</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {visible.map((change) => (
              <tr key={`${change.kind}:${change.row.qid}`}>
                <td>
                  <QubitTile qid={change.row.qid} />
                </td>
                <td className="text-right font-mono">
                  {formatParameterValue(change.row.value_before)}
                </td>
                <td className="text-right font-mono">
                  {formatParameterValue(change.row.value_after)}
                </td>
                <td className="text-right font-mono text-base-content/70">{changeText(change)}</td>
                <td className="text-right">
                  <button
                    type="button"
                    className="btn btn-ghost btn-xs"
                    onClick={() =>
                      onSelect({ parameterName: group.parameterName, qid: change.row.qid })
                    }
                    aria-label={`Lineage of ${group.parameterName} ${change.row.qid}`}
                  >
                    Lineage
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {group.targets.length > visible.length && (
          <button
            type="button"
            className="btn btn-ghost btn-xs w-full rounded-t-none"
            onClick={() => setShowAll(true)}
          >
            Show all {group.targets.length} targets
          </button>
        )}
      </div>
    </details>
  );
}

/**
 * Values this execution wrote to the calibration database, compared with the run published just
 * before it. Changes are grouped by parameter, ordered by the largest relative change, so a
 * chip-wide run stays readable; expanding a parameter lists its targets, each with its lineage.
 */
export function ExecutionParameterChanges({ executionId }: { executionId: string }) {
  const {
    data: executionsResponse,
    isLoading: isListLoading,
    isError: isListError,
  } = useGetRecentExecutions({ limit: EXECUTION_WINDOW });
  const executions = useMemo(
    () => executionsResponse?.data?.executions ?? [],
    [executionsResponse],
  );
  const index = executions.findIndex((execution) => execution.execution_id === executionId);
  const previousId = index >= 0 ? executions[index + 1]?.execution_id : undefined;
  const { data, isLoading, isError } = useCompareExecutions(
    { execution_id_before: previousId ?? "", execution_id_after: executionId },
    { query: { enabled: !!previousId } },
  );
  const [target, setTarget] = useState<ProvenanceTarget | null>(null);
  const diff = data?.data;
  const groups = useMemo(() => (diff ? groupByParameter(diff) : []), [diff]);

  if (isListLoading || (previousId && isLoading)) {
    return <div className="skeleton h-16 w-full" />;
  }
  if (isListError) {
    return (
      <p role="alert" className="text-sm text-base-content/60">
        Parameter changes could not be loaded.
      </p>
    );
  }
  if (index < 0) {
    return (
      <p className="text-sm text-base-content/60">
        No values published by this run were found among the last {EXECUTION_WINDOW} recorded runs.
      </p>
    );
  }
  if (!previousId) {
    return (
      <p className="text-sm text-base-content/60">
        First run with published values; there is no earlier run to compare against.
      </p>
    );
  }
  if (isError || !diff) {
    return (
      <p role="alert" className="text-sm text-base-content/60">
        Parameter changes could not be loaded.
      </p>
    );
  }

  const targetCount = groups.reduce((sum, group) => sum + group.targets.length, 0);
  return (
    <div className="space-y-3 text-sm">
      <p className="text-base-content/60">
        Compared with <span className="font-mono text-base-content">{previousId}</span>:{" "}
        {groups.length} parameters differ on {targetCount} targets, largest change first. Expand a
        parameter for its targets and their lineage.
      </p>
      {groups.length === 0 ? (
        <p className="text-base-content/60">No published value differs from the previous run.</p>
      ) : (
        <div className="space-y-2">
          {groups.map((group) => (
            <ParameterGroupRow key={group.parameterName} group={group} onSelect={setTarget} />
          ))}
        </div>
      )}
      <ParameterLineageDialog target={target} onClose={() => setTarget(null)} />
    </div>
  );
}
