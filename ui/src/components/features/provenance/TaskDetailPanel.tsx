"use client";

import { useMemo } from "react";
import { X } from "lucide-react";
import type { LineageNodeResponse, LineageEdgeResponse } from "@/schemas";
import { TaskFigure } from "@/components/charts/TaskFigure";

interface TaskDetailPanelProps {
  /** The graph node_id of the selected activity */
  activityNodeId: string;
  /** All nodes from the API (unfiltered) */
  nodes: LineageNodeResponse[];
  /** All edges from the API (unfiltered by hops/derived toggle) */
  edges: LineageEdgeResponse[];
  /** Called when the close button is clicked */
  onClose: () => void;
}

interface ParameterInfo {
  nodeId: string;
  name: string;
  value: string;
  unit: string;
  qid: string;
}

const EXPONENTIAL_THRESHOLD_LOW = 0.01;
const EXPONENTIAL_THRESHOLD_HIGH = 10000;
const DECIMAL_PLACES = 4;
const EXPONENTIAL_DIGITS = 2;

function formatValue(value: unknown): string {
  if (value === undefined || value === null) return "";
  if (typeof value === "number") {
    if (
      Math.abs(value) < EXPONENTIAL_THRESHOLD_LOW ||
      Math.abs(value) > EXPONENTIAL_THRESHOLD_HIGH
    ) {
      return value.toExponential(EXPONENTIAL_DIGITS);
    }
    return value.toFixed(DECIMAL_PLACES);
  }
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

export function TaskDetailPanel({
  activityNodeId,
  nodes,
  edges,
  onClose,
}: TaskDetailPanelProps) {
  const activityNode = useMemo(
    () => nodes.find((n) => n.node_id === activityNodeId),
    [nodes, activityNodeId],
  );

  const nodeMap = useMemo(() => {
    const m = new Map<string, LineageNodeResponse>();
    for (const n of nodes) m.set(n.node_id, n);
    return m;
  }, [nodes]);

  // Input: edges where relation_type == "used" and source_id == activityNodeId
  //   → target_id is the input entity
  const inputParams = useMemo<ParameterInfo[]>(() => {
    return edges
      .filter(
        (e) => e.relation_type === "used" && e.source_id === activityNodeId,
      )
      .map((e) => {
        const node = nodeMap.get(e.target_id);
        if (!node?.entity) return null;
        return {
          nodeId: node.node_id,
          name: node.entity.parameter_name || node.node_id,
          value: formatValue(node.entity.value),
          unit: node.entity.unit ?? "",
          qid: node.entity.qid ?? "",
        };
      })
      .filter((p): p is ParameterInfo => p !== null);
  }, [edges, activityNodeId, nodeMap]);

  // Output: edges where relation_type == "wasGeneratedBy" and target_id == activityNodeId
  //   → source_id is the output entity
  const outputParams = useMemo<ParameterInfo[]>(() => {
    return edges
      .filter(
        (e) =>
          e.relation_type === "wasGeneratedBy" &&
          e.target_id === activityNodeId,
      )
      .map((e) => {
        const node = nodeMap.get(e.source_id);
        if (!node?.entity) return null;
        return {
          nodeId: node.node_id,
          name: node.entity.parameter_name || node.node_id,
          value: formatValue(node.entity.value),
          unit: node.entity.unit ?? "",
          qid: node.entity.qid ?? "",
        };
      })
      .filter((p): p is ParameterInfo => p !== null);
  }, [edges, activityNodeId, nodeMap]);

  const activity = activityNode?.activity;
  const taskName = activity?.task_name ?? activityNodeId;
  const status = activity?.status;
  const qid = activity?.qid;

  const statusBadge = status ? (
    <span
      className={`badge badge-sm ${
        status === "completed"
          ? "badge-success"
          : status === "failed"
            ? "badge-error"
            : status === "running"
              ? "badge-info"
              : "badge-warning"
      }`}
    >
      {status}
    </span>
  ) : null;

  const hasFigure = !!(activity?.task_id && qid);

  return (
    <div className="w-80 flex-shrink-0 bg-base-100 border-l border-base-300 flex flex-col overflow-hidden">
      {/* Header */}
      <div className="bg-secondary/10 px-4 py-3 border-b border-base-300 flex-shrink-0">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="font-semibold text-sm truncate">{taskName}</div>
            <div className="flex items-center gap-2 mt-1">
              {statusBadge}
              {qid && (
                <span className="badge badge-outline badge-sm">{qid}</span>
              )}
            </div>
          </div>
          <button
            className="btn btn-ghost btn-xs flex-shrink-0"
            onClick={onClose}
            aria-label="Close detail panel"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
      </div>

      {/* Result Figure (top, scrollable) */}
      {hasFigure && (
        <div className="min-h-0 max-h-[50%] overflow-y-auto border-b border-base-300 p-2">
          <div className="rounded-lg border border-base-300 overflow-hidden">
            <TaskFigure
              taskId={activity!.task_id}
              qid={qid!}
              className="w-full h-auto"
            />
          </div>
        </div>
      )}

      {/* Scrollable parameters */}
      <div className="flex-1 overflow-y-auto p-3 space-y-4">
        {/* Output Parameters */}
        <section>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-1 h-4 rounded bg-green-500" />
            <h4 className="text-xs font-semibold uppercase tracking-wide text-base-content/60">
              Output Parameters
            </h4>
            <span className="badge badge-ghost badge-xs">
              {outputParams.length}
            </span>
          </div>
          {outputParams.length === 0 ? (
            <div className="text-xs text-base-content/40 pl-3">
              No output parameters
            </div>
          ) : (
            <div className="space-y-1">
              {outputParams.map((p) => (
                <div
                  key={p.nodeId}
                  className="px-3 py-2 rounded-lg border border-green-500/20 bg-green-500/5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium truncate">
                      {p.name}
                    </span>
                    {p.qid && (
                      <span className="badge badge-outline badge-xs flex-shrink-0">
                        {p.qid}
                      </span>
                    )}
                  </div>
                  {p.value && (
                    <div className="text-xs font-mono text-base-content/60 mt-0.5">
                      {p.value} {p.unit}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Input Parameters */}
        <section>
          <div className="flex items-center gap-2 mb-2">
            <div className="w-1 h-4 rounded bg-amber-500" />
            <h4 className="text-xs font-semibold uppercase tracking-wide text-base-content/60">
              Input Parameters
            </h4>
            <span className="badge badge-ghost badge-xs">
              {inputParams.length}
            </span>
          </div>
          {inputParams.length === 0 ? (
            <div className="text-xs text-base-content/40 pl-3">
              No input parameters
            </div>
          ) : (
            <div className="space-y-1">
              {inputParams.map((p) => (
                <div
                  key={p.nodeId}
                  className="px-3 py-2 rounded-lg border border-amber-500/20 bg-amber-500/5"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium truncate">
                      {p.name}
                    </span>
                    {p.qid && (
                      <span className="badge badge-outline badge-xs flex-shrink-0">
                        {p.qid}
                      </span>
                    )}
                  </div>
                  {p.value && (
                    <div className="text-xs font-mono text-base-content/60 mt-0.5">
                      {p.value} {p.unit}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}
