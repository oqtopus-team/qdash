"use client";

import { useMemo, useState } from "react";

import {
  ImageOff,
  ArrowDown,
  Plus,
  Minus,
  Pen,
  Check,
  ChevronRight,
  Eye,
  EyeOff,
} from "lucide-react";

import { TaskFigure } from "@/components/charts/TaskFigure";
import type { LineageResponse } from "@/schemas/lineageResponse";

type StepStatus = "changed" | "unchanged" | "added" | "removed";

interface MatchedStep {
  taskName: string;
  qid: string;
  depthBefore: number | null;
  depthAfter: number | null;
  taskIdBefore?: string;
  taskIdAfter?: string;
  executionIdBefore?: string;
  executionIdAfter?: string;
  paramBefore?: { name: string; value: number | string; unit?: string };
  paramAfter?: { name: string; value: number | string; unit?: string };
  status: StepStatus;
}

interface LineagePathComparisonProps {
  lineageBefore: LineageResponse;
  lineageAfter: LineageResponse;
  labelBefore: string;
  labelAfter: string;
}

function valuesEqual(
  a: number | string | undefined,
  b: number | string | undefined,
): boolean {
  if (a === undefined && b === undefined) return true;
  if (a === undefined || b === undefined) return false;
  if (typeof a === "number" && typeof b === "number") {
    // Treat as equal if relative difference < 1e-9
    if (a === 0 && b === 0) return true;
    return Math.abs(a - b) / Math.max(Math.abs(a), Math.abs(b)) < 1e-9;
  }
  return a === b;
}

export function LineagePathComparison({
  lineageBefore,
  lineageAfter,
  labelBefore,
  labelAfter,
}: LineagePathComparisonProps) {
  const [showUnchanged, setShowUnchanged] = useState(false);

  const matchedSteps = useMemo(() => {
    type ActivityInfo = {
      taskName: string;
      qid: string;
      taskId: string;
      executionId: string;
      depth: number;
    };

    const extractActivities = (lineage: LineageResponse): ActivityInfo[] =>
      lineage.nodes
        .filter((n) => n.node_type === "activity" && n.activity)
        .map((n) => ({
          taskName: n.activity!.task_name,
          qid: n.activity!.qid ?? "",
          taskId: n.activity!.task_id,
          executionId: n.activity!.execution_id,
          depth: n.depth ?? 0,
        }));

    type EntityInfo = { name: string; value: number | string; unit?: string };

    const buildOutputMap = (
      lineage: LineageResponse,
    ): Map<string, EntityInfo> => {
      const map = new Map<string, EntityInfo>();
      const entityMap = new Map(
        lineage.nodes
          .filter((n) => n.node_type === "entity" && n.entity)
          .map((n) => [n.node_id, n.entity!]),
      );
      for (const edge of lineage.edges) {
        if (edge.relation_type === "wasGeneratedBy") {
          const entity = entityMap.get(edge.source_id);
          if (entity) {
            map.set(edge.target_id, {
              name: entity.parameter_name ?? "",
              value: entity.value,
              unit: entity.unit ?? undefined,
            });
          }
        }
      }
      return map;
    };

    const beforeActivities = extractActivities(lineageBefore);
    const afterActivities = extractActivities(lineageAfter);
    const beforeOutputs = buildOutputMap(lineageBefore);
    const afterOutputs = buildOutputMap(lineageAfter);

    const beforeMap = new Map<string, ActivityInfo & { output?: EntityInfo }>();
    for (const a of beforeActivities) {
      const key = `${a.taskName}:${a.qid}`;
      if (!beforeMap.has(key)) {
        const nodeId = lineageBefore.nodes.find(
          (n) => n.activity?.task_id === a.taskId,
        )?.node_id;
        beforeMap.set(key, {
          ...a,
          output: nodeId ? beforeOutputs.get(nodeId) : undefined,
        });
      }
    }

    const afterMap = new Map<string, ActivityInfo & { output?: EntityInfo }>();
    for (const a of afterActivities) {
      const key = `${a.taskName}:${a.qid}`;
      if (!afterMap.has(key)) {
        const nodeId = lineageAfter.nodes.find(
          (n) => n.activity?.task_id === a.taskId,
        )?.node_id;
        afterMap.set(key, {
          ...a,
          output: nodeId ? afterOutputs.get(nodeId) : undefined,
        });
      }
    }

    const allKeys = new Set([...beforeMap.keys(), ...afterMap.keys()]);
    const steps: MatchedStep[] = [];

    for (const key of allKeys) {
      const b = beforeMap.get(key);
      const a = afterMap.get(key);
      const [taskName, qid] = key.split(":");

      let status: StepStatus;
      if (b && a) {
        const paramChanged = !valuesEqual(b.output?.value, a.output?.value);
        status = paramChanged ? "changed" : "unchanged";
      } else if (a) {
        status = "added";
      } else {
        status = "removed";
      }

      steps.push({
        taskName,
        qid,
        depthBefore: b?.depth ?? null,
        depthAfter: a?.depth ?? null,
        taskIdBefore: b?.taskId,
        taskIdAfter: a?.taskId,
        executionIdBefore: b?.executionId,
        executionIdAfter: a?.executionId,
        paramBefore: b?.output,
        paramAfter: a?.output,
        status,
      });
    }

    steps.sort((a, b) => {
      const dA = Math.min(a.depthBefore ?? 999, a.depthAfter ?? 999);
      const dB = Math.min(b.depthBefore ?? 999, b.depthAfter ?? 999);
      if (dA !== dB) return dA - dB;
      return a.taskName.localeCompare(b.taskName);
    });

    return steps;
  }, [lineageBefore, lineageAfter]);

  const counts = useMemo(() => {
    const c = { changed: 0, unchanged: 0, added: 0, removed: 0 };
    for (const s of matchedSteps) c[s.status]++;
    return c;
  }, [matchedSteps]);

  if (matchedSteps.length === 0) {
    return (
      <div className="text-center py-8 text-base-content/50">
        No activities found in the lineage paths
      </div>
    );
  }

  const formatValue = (value: number | string) => {
    if (typeof value === "number") return value.toExponential(4);
    return String(value);
  };

  const statusConfig: Record<
    StepStatus,
    {
      border: string;
      badge: string;
      label: string;
      icon: typeof Pen;
      bg: string;
    }
  > = {
    changed: {
      border: "border-warning/50",
      badge: "badge-warning",
      label: "Changed",
      icon: Pen,
      bg: "",
    },
    unchanged: {
      border: "border-base-300",
      badge: "badge-ghost",
      label: "Unchanged",
      icon: Check,
      bg: "opacity-60",
    },
    added: {
      border: "border-success/50",
      badge: "badge-success",
      label: "Added",
      icon: Plus,
      bg: "",
    },
    removed: {
      border: "border-error/50",
      badge: "badge-error",
      label: "Removed",
      icon: Minus,
      bg: "",
    },
  };

  return (
    <div className="space-y-4">
      {/* Summary bar */}
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span className="text-base-content/60">
          {labelBefore} → {labelAfter}
        </span>
        <div className="flex items-center gap-2">
          {counts.changed > 0 && (
            <span className="badge badge-warning badge-sm gap-1">
              <Pen className="h-3 w-3" />
              {counts.changed} changed
            </span>
          )}
          {counts.added > 0 && (
            <span className="badge badge-success badge-sm gap-1">
              <Plus className="h-3 w-3" />
              {counts.added} added
            </span>
          )}
          {counts.removed > 0 && (
            <span className="badge badge-error badge-sm gap-1">
              <Minus className="h-3 w-3" />
              {counts.removed} removed
            </span>
          )}
          {counts.unchanged > 0 && (
            <button
              className="badge badge-ghost badge-sm gap-1 cursor-pointer hover:badge-outline transition-colors"
              onClick={() => setShowUnchanged((v) => !v)}
            >
              {showUnchanged ? (
                <EyeOff className="h-3 w-3" />
              ) : (
                <Eye className="h-3 w-3" />
              )}
              {counts.unchanged} unchanged
            </button>
          )}
        </div>
      </div>

      {/* Steps */}
      {matchedSteps.map((step, idx) => {
        const config = statusConfig[step.status];
        const isUnchanged = step.status === "unchanged";

        // Hide unchanged steps unless toggled
        if (isUnchanged && !showUnchanged) {
          // Show a collapsed placeholder for consecutive unchanged steps
          const prevStep = idx > 0 ? matchedSteps[idx - 1] : null;
          const isPrevHidden =
            prevStep?.status === "unchanged" && !showUnchanged;
          if (isPrevHidden) return null; // Only show one placeholder per group

          // Count consecutive unchanged steps from here
          let count = 0;
          for (let i = idx; i < matchedSteps.length; i++) {
            if (matchedSteps[i].status === "unchanged") count++;
            else break;
          }

          return (
            <div key={`${step.taskName}:${step.qid}`}>
              {idx > 0 && (
                <div className="flex justify-center py-1">
                  <ArrowDown className="h-4 w-4 text-base-content/20" />
                </div>
              )}
              <button
                className="w-full flex items-center justify-center gap-2 py-2 px-4 rounded-lg border border-dashed border-base-300 text-base-content/40 hover:text-base-content/60 hover:border-base-content/30 transition-colors text-xs"
                onClick={() => setShowUnchanged(true)}
              >
                <Check className="h-3 w-3" />
                {count} unchanged experiment{count !== 1 && "s"} — click to
                expand
              </button>
            </div>
          );
        }

        const StatusIcon = config.icon;

        return (
          <div key={`${step.taskName}:${step.qid}`} className={config.bg}>
            {idx > 0 && (
              <div className="flex justify-center py-1">
                <ArrowDown className="h-4 w-4 text-base-content/20" />
              </div>
            )}

            <div className={`card bg-base-200 border-2 ${config.border}`}>
              <div className="card-body p-4">
                {/* Header */}
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <StatusIcon className="h-3.5 w-3.5" />
                    <h4 className="font-medium text-sm">{step.taskName}</h4>
                    <span className="badge badge-outline badge-xs font-mono">
                      {step.qid}
                    </span>
                    {step.depthBefore !== null && (
                      <span className="text-xs text-base-content/40">
                        depth {step.depthBefore}
                      </span>
                    )}
                  </div>
                  <span className={`badge ${config.badge} badge-sm`}>
                    {config.label}
                  </span>
                </div>

                {/* Parameter output comparison */}
                {(step.paramBefore || step.paramAfter) && (
                  <div className="flex items-center gap-2 text-xs bg-base-300/50 rounded-lg p-2 flex-wrap">
                    <span className="text-base-content/60">
                      {step.paramBefore?.name || step.paramAfter?.name}:
                    </span>
                    {step.paramBefore && (
                      <span className="font-mono">
                        {formatValue(step.paramBefore.value)}
                        {step.paramBefore.unit
                          ? ` ${step.paramBefore.unit}`
                          : ""}
                      </span>
                    )}
                    {step.paramBefore && step.paramAfter && (
                      <ChevronRight className="h-3 w-3 text-base-content/40" />
                    )}
                    {step.paramAfter && (
                      <span
                        className={`font-mono ${
                          step.status === "changed"
                            ? "text-warning font-semibold"
                            : ""
                        }`}
                      >
                        {formatValue(step.paramAfter.value)}
                        {step.paramAfter.unit ? ` ${step.paramAfter.unit}` : ""}
                      </span>
                    )}
                  </div>
                )}

                {/* Side-by-side figures — skip for unchanged to keep compact */}
                {!isUnchanged && (
                  <div className="grid grid-cols-1 lg:grid-cols-2 gap-3 mt-1">
                    {/* Before */}
                    <div>
                      <div className="text-xs text-base-content/60 mb-1">
                        {labelBefore}
                        {step.executionIdBefore && (
                          <span className="font-mono ml-1">
                            ({step.executionIdBefore.slice(0, 12)})
                          </span>
                        )}
                      </div>
                      {step.taskIdBefore ? (
                        <div className="bg-base-100 rounded-lg p-1">
                          <TaskFigure
                            taskId={step.taskIdBefore}
                            qid={step.qid}
                            className="w-full rounded"
                          />
                        </div>
                      ) : (
                        <div className="flex flex-col items-center justify-center h-32 bg-base-300/50 rounded-lg">
                          <ImageOff className="h-6 w-6 text-base-content/20 mb-1" />
                          <span className="text-xs text-base-content/30">
                            Not in this path
                          </span>
                        </div>
                      )}
                    </div>

                    {/* After */}
                    <div>
                      <div className="text-xs text-base-content/60 mb-1">
                        {labelAfter}
                        {step.executionIdAfter && (
                          <span className="font-mono ml-1">
                            ({step.executionIdAfter.slice(0, 12)})
                          </span>
                        )}
                      </div>
                      {step.taskIdAfter ? (
                        <div className="bg-base-100 rounded-lg p-1">
                          <TaskFigure
                            taskId={step.taskIdAfter}
                            qid={step.qid}
                            className="w-full rounded"
                          />
                        </div>
                      ) : (
                        <div className="flex flex-col items-center justify-center h-32 bg-base-300/50 rounded-lg">
                          <ImageOff className="h-6 w-6 text-base-content/20 mb-1" />
                          <span className="text-xs text-base-content/30">
                            Not in this path
                          </span>
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
