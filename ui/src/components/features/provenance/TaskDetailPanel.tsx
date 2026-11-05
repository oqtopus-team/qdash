"use client";

import { useCallback, useMemo } from "react";

import { X } from "lucide-react";

import { TaskFigure } from "@/components/charts/TaskFigure";
import { QubitTile } from "@/components/ui/QubitTile";
import { formatParameterValue } from "@/lib/formatParameterValue";
import type { LineageEdgeResponse, LineageNodeResponse } from "@/schemas";

interface TaskDetailPanelProps {
  /** Graph node id of the selected task. */
  activityNodeId: string;
  /** Every node of the graph, before any hop or search filtering. */
  nodes: LineageNodeResponse[];
  /** Every edge of the graph, before any filtering. */
  edges: LineageEdgeResponse[];
  onClose: () => void;
}

function ParameterRows({ title, nodes }: { title: string; nodes: LineageNodeResponse[] }) {
  return (
    <section aria-label={title}>
      <h4 className="text-xs font-medium text-base-content/60">
        {title} ({nodes.length})
      </h4>
      {nodes.length === 0 ? (
        <p className="mt-1 text-xs text-base-content/50">None</p>
      ) : (
        <ul className="mt-1 divide-y divide-base-300 rounded-lg border border-base-300">
          {nodes.map((node) => {
            const entity = node.entity!;
            return (
              <li key={node.node_id} className="flex items-center gap-2 px-2.5 py-1.5 text-xs">
                <QubitTile qid={entity.qid ?? ""} />
                <span className="min-w-0 flex-1 truncate font-medium">{entity.parameter_name}</span>
                <span className="font-mono">{formatParameterValue(entity.value, entity.unit)}</span>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

/** What one task in the graph read and wrote, with its figure when it has one. */
export function TaskDetailPanel({ activityNodeId, nodes, edges, onClose }: TaskDetailPanelProps) {
  const nodeById = useMemo(() => new Map(nodes.map((node) => [node.node_id, node])), [nodes]);
  const activity = nodeById.get(activityNodeId)?.activity;

  const entitiesOn = useCallback(
    (pick: (edge: LineageEdgeResponse) => string | null) =>
      edges
        .map(pick)
        .filter((id): id is string => !!id)
        .map((id) => nodeById.get(id))
        .filter((node): node is LineageNodeResponse => !!node?.entity),
    [edges, nodeById],
  );
  const inputs = useMemo(
    () =>
      entitiesOn((edge) =>
        edge.relation_type === "used" && edge.source_id === activityNodeId ? edge.target_id : null,
      ),
    [entitiesOn, activityNodeId],
  );
  const outputs = useMemo(
    () =>
      entitiesOn((edge) =>
        edge.relation_type === "wasGeneratedBy" && edge.target_id === activityNodeId
          ? edge.source_id
          : null,
      ),
    [entitiesOn, activityNodeId],
  );

  const status = activity?.status;
  const statusClass =
    status === "failed" ? "text-error" : status === "completed" ? "text-base-content/60" : "";

  return (
    <aside
      aria-label="Task details"
      className="flex w-80 shrink-0 flex-col overflow-hidden border-l border-base-300 bg-base-100"
    >
      <div className="flex items-start justify-between gap-2 border-b border-base-300 px-4 py-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium">
            {activity?.task_name ?? activityNodeId}
          </div>
          <div className="mt-1 flex items-center gap-2 text-xs">
            {activity?.qid && <QubitTile qid={activity.qid} />}
            {status && <span className={statusClass}>{status}</span>}
          </div>
        </div>
        <button
          type="button"
          className="btn btn-ghost btn-xs btn-circle"
          onClick={onClose}
          aria-label="Close task details"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-3">
        {activity?.task_id && activity.qid && (
          <div className="h-44 rounded-lg border border-base-300 bg-base-100 p-1">
            <TaskFigure taskId={activity.task_id} qid={activity.qid} fit />
          </div>
        )}
        <ParameterRows title="Wrote" nodes={outputs} />
        <ParameterRows title="Read" nodes={inputs} />
      </div>
    </aside>
  );
}
