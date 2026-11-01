"use client";

import { useMemo, useState } from "react";

import Link from "next/link";
import { ArrowLeft, ExternalLink, GitBranch } from "lucide-react";

import {
  useGetParameterHistory,
  useGetProvenanceImpact,
  useGetProvenanceLineage,
} from "@/client/provenance/provenance";
import { QubitTile } from "@/components/ui/QubitTile";
import { formatParameterValue } from "@/lib/formatParameterValue";
import type { ProvenanceTarget } from "@/lib/provenanceTarget";
import { formatDateTime } from "@/lib/utils/datetime";
import type { LineageEdgeResponse, LineageNodeResponse, ParameterVersionResponse } from "@/schemas";

import { LineageGraphDialog } from "./LineageGraphDialog";

/** Only the values a run read and the values derived from it; the full graph is a separate view. */
const DIRECT_HOPS = 1;
/** Versions offered in the version selector. */
const VERSION_LIMIT = 50;

/** One step of in-panel exploration: a parameter and, optionally, the exact version to show. */
interface LineageFocus extends ProvenanceTarget {
  entityId?: string;
}

interface ParameterLineagePanelProps extends ProvenanceTarget {
  /** Open on this version (an entity ID) rather than the current one. */
  entityId?: string;
  /**
   * Hide the list of inputs while the panel shows the value it was opened on. A task result page
   * already lists the same values in its input parameter table; the dialog opened from a metric
   * has no such table and keeps them.
   */
  hideInputs?: boolean;
  /** Task result the panel sits on; its own link is left out. */
  currentTaskId?: string;
}

interface Graph {
  nodes: LineageNodeResponse[];
  edges: LineageEdgeResponse[];
}

/** What produced a value: the task name, or the kind of manual operation. */
function producerName(producer: LineageNodeResponse | null, version: ParameterVersionResponse) {
  const activity = producer?.activity;
  if (activity?.task_type === "manual_edit") return "Manual edit";
  if (activity?.task_type === "seed_import") return "Seed import";
  return activity?.task_name || version.task_name || "an unrecorded task";
}

/** Entities reached through the edges `pick` accepts, deduplicated and sorted by parameter. */
function linkedEntities(
  graph: Graph | undefined,
  pick: (edge: LineageEdgeResponse) => string | null,
): LineageNodeResponse[] {
  if (!graph) return [];
  const byId = new Map(graph.nodes.map((node) => [node.node_id, node]));
  const seen = new Set<string>();
  const result: LineageNodeResponse[] = [];
  for (const edge of graph.edges) {
    const id = pick(edge);
    if (!id || seen.has(id)) continue;
    const node = byId.get(id);
    if (!node || node.node_type !== "entity" || !node.entity) continue;
    seen.add(id);
    result.push(node);
  }
  return result.sort(
    (a, b) =>
      a.entity!.parameter_name.localeCompare(b.entity!.parameter_name) ||
      (a.entity!.qid ?? "").localeCompare(b.entity!.qid ?? "", undefined, { numeric: true }),
  );
}

/** Rows shown before the list folds behind a "Show all" button. */
const VISIBLE_ROWS = 8;

function EntityList({
  title,
  hint,
  nodes,
  loading,
  empty,
  onOpen,
}: {
  title: string;
  hint: string;
  nodes: LineageNodeResponse[];
  loading: boolean;
  empty: string;
  onOpen: (node: LineageNodeResponse) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? nodes : nodes.slice(0, VISIBLE_ROWS);
  return (
    <section aria-label={title}>
      <h4 className="text-xs font-medium text-base-content/60">
        {title}
        {!loading && ` (${nodes.length})`}
      </h4>
      <p className="text-xs text-base-content/50">{hint}</p>
      {loading ? (
        <div className="skeleton mt-1.5 h-8 w-full" />
      ) : nodes.length === 0 ? (
        <p className="mt-1.5 text-xs text-base-content/60">{empty}</p>
      ) : (
        <ul className="mt-1.5 divide-y divide-base-300 rounded-lg border border-base-300">
          {visible.map((node) => {
            const entity = node.entity!;
            return (
              <li key={node.node_id}>
                <button
                  type="button"
                  onClick={() => onOpen(node)}
                  className="flex w-full items-center gap-2 px-2.5 py-1.5 text-left text-xs hover:bg-base-200"
                >
                  <QubitTile qid={entity.qid ?? ""} />
                  <span className="min-w-0 flex-1 truncate font-medium">
                    {entity.parameter_name}
                  </span>
                  <span className="font-mono">
                    {formatParameterValue(entity.value, entity.unit)}
                  </span>
                  <span className="text-base-content/50">v{entity.version}</span>
                  <span className="hidden max-w-32 truncate text-base-content/50 sm:inline">
                    {entity.task_name}
                  </span>
                </button>
              </li>
            );
          })}
          {nodes.length > visible.length && (
            <li>
              <button
                type="button"
                className="btn btn-ghost btn-xs w-full rounded-t-none"
                onClick={() => setExpanded(true)}
              >
                Show all {nodes.length}
              </button>
            </li>
          )}
        </ul>
      )}
    </section>
  );
}

/**
 * Where one parameter value came from and what depends on it: the task that produced it, the
 * current values that task read, and the values derived from it. Rows open the same view for the
 * neighbouring value, so a chain can be followed in place; the full graph opens on demand.
 */
export function ParameterLineagePanel({
  parameterName,
  qid,
  entityId,
  hideInputs = false,
  currentTaskId,
}: ParameterLineagePanelProps) {
  const [trail, setTrail] = useState<LineageFocus[]>([{ parameterName, qid, entityId }]);
  const focus = trail[trail.length - 1];
  const [pickedEntityId, setPickedEntityId] = useState<string | null>(null);
  const [graphOpen, setGraphOpen] = useState(false);

  const {
    data: historyResponse,
    isLoading: isHistoryLoading,
    isError: isHistoryError,
  } = useGetParameterHistory(
    { parameter_name: focus.parameterName, qid: focus.qid, limit: VERSION_LIMIT },
    { query: { enabled: !!focus.parameterName && !!focus.qid } },
  );
  const versions = useMemo(() => historyResponse?.data?.versions ?? [], [historyResponse]);
  const requestedEntityId = pickedEntityId ?? focus.entityId ?? null;
  const requestedVersion = requestedEntityId
    ? versions.find((version) => version.entity_id === requestedEntityId)
    : undefined;
  const version = requestedVersion ?? versions[0];
  const currentEntityId = version?.entity_id ?? "";
  // The caller named a run that did not publish this parameter; the current value stands in.
  const requestedMissing = !!focus.entityId && !pickedEntityId && !!version && !requestedVersion;

  const { data: lineageResponse, isLoading: isLineageLoading } = useGetProvenanceLineage(
    currentEntityId,
    { max_depth: DIRECT_HOPS },
    { query: { enabled: !!currentEntityId } },
  );
  const { data: impactResponse, isLoading: isImpactLoading } = useGetProvenanceImpact(
    currentEntityId,
    { max_depth: DIRECT_HOPS },
    { query: { enabled: !!currentEntityId } },
  );
  const lineage = lineageResponse?.data;
  const impact = impactResponse?.data;

  const producer = useMemo(() => {
    const edge = lineage?.edges.find(
      (candidate) =>
        candidate.relation_type === "wasGeneratedBy" && candidate.source_id === currentEntityId,
    );
    return edge ? (lineage?.nodes.find((node) => node.node_id === edge.target_id) ?? null) : null;
  }, [lineage, currentEntityId]);
  const inputs = useMemo(
    () =>
      linkedEntities(lineage, (edge) =>
        edge.relation_type === "wasDerivedFrom" && edge.source_id === currentEntityId
          ? edge.target_id
          : null,
      ),
    [lineage, currentEntityId],
  );
  const dependents = useMemo(
    () =>
      linkedEntities(impact, (edge) =>
        edge.relation_type === "wasDerivedFrom" && edge.target_id === currentEntityId
          ? edge.source_id
          : null,
      ),
    [impact, currentEntityId],
  );
  const enteredByHand =
    producer?.activity?.task_type === "manual_edit" ||
    producer?.activity?.task_type === "seed_import";

  const openEntity = (node: LineageNodeResponse) => {
    const entity = node.entity!;
    setPickedEntityId(null);
    setTrail((current) => [
      ...current,
      { parameterName: entity.parameter_name, qid: entity.qid ?? "", entityId: entity.entity_id },
    ]);
  };
  const goBack = () => {
    setPickedEntityId(null);
    setTrail((current) => (current.length > 1 ? current.slice(0, -1) : current));
  };
  const backButton = trail.length > 1 && (
    <button type="button" className="btn btn-ghost btn-xs -ml-2 gap-1" onClick={goBack}>
      <ArrowLeft className="h-3.5 w-3.5" />
      Back to {trail[trail.length - 2].parameterName}
    </button>
  );

  if (isHistoryLoading) {
    return (
      <div className="flex justify-center py-8">
        <span className="loading loading-spinner" />
      </div>
    );
  }
  if (isHistoryError) {
    return (
      <p role="alert" className="text-sm text-base-content/60">
        Lineage could not be loaded.
      </p>
    );
  }
  if (!version) {
    return (
      <div className="space-y-2 text-sm">
        {backButton}
        <div className="flex items-center gap-2">
          <span className="font-medium">{focus.parameterName}</span>
          <QubitTile qid={focus.qid} />
        </div>
        <p className="text-base-content/60">
          No published version is recorded. A value appears here once a task writes it to the
          calibration database.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-4 text-sm">
      {backButton}

      <div>
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-medium">{version.parameter_name}</span>
          <QubitTile qid={version.qid ?? ""} />
          <span className="font-mono">{formatParameterValue(version.value, version.unit)}</span>
          {version.error ? (
            <span className="font-mono text-xs text-base-content/50">
              ±{formatParameterValue(version.error)}
            </span>
          ) : null}
          {versions.length > 1 ? (
            <select
              aria-label="Version"
              className="select select-bordered select-xs font-mono"
              value={currentEntityId}
              onChange={(event) => setPickedEntityId(event.target.value)}
            >
              {versions.map((candidate) => (
                <option key={candidate.entity_id} value={candidate.entity_id}>
                  v{candidate.version}
                  {candidate.valid_until ? "" : " (current)"}
                </option>
              ))}
            </select>
          ) : (
            <span className="badge badge-ghost badge-sm font-mono">v{version.version}</span>
          )}
        </div>
        {requestedMissing && (
          <p className="mt-1 text-xs text-base-content/60">
            This run did not publish {focus.parameterName}; showing the current version.
          </p>
        )}
        <p className="mt-1 text-xs text-base-content/60">
          Produced by{" "}
          <span className="font-medium text-base-content">{producerName(producer, version)}</span>{" "}
          on {formatDateTime(version.valid_from)}
          {version.valid_until ? `, replaced ${formatDateTime(version.valid_until)}` : ""}.
        </p>
        <div className="mt-2 flex flex-wrap gap-2">
          {version.task_id && version.task_id !== currentTaskId && (
            <Link
              href={`/task-results/${encodeURIComponent(version.task_id)}`}
              className="btn btn-ghost btn-xs gap-1"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              Task result
            </Link>
          )}
          {version.chip_id && version.execution_id && (
            <Link
              href={`/execution/${encodeURIComponent(version.chip_id)}/${encodeURIComponent(version.execution_id)}`}
              className="btn btn-ghost btn-xs gap-1"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              Execution
            </Link>
          )}
          <button
            type="button"
            className="btn btn-ghost btn-xs gap-1"
            onClick={() => setGraphOpen(true)}
          >
            <GitBranch className="h-3.5 w-3.5" />
            Full graph
          </button>
        </div>
      </div>

      {!(hideInputs && trail.length === 1) && (
        <EntityList
          title="Inputs"
          hint="Current values the producing task read."
          nodes={inputs}
          loading={isLineageLoading}
          empty={
            enteredByHand ? "Entered by hand, so there are no inputs." : "No inputs were recorded."
          }
          onOpen={openEntity}
        />
      )}
      <EntityList
        title="Depends on this value"
        hint="Values derived from it; re-run their tasks after changing it."
        nodes={dependents}
        loading={isImpactLoading}
        empty="Nothing has been derived from this value."
        onOpen={openEntity}
      />

      <LineageGraphDialog
        open={graphOpen}
        onClose={() => setGraphOpen(false)}
        entityId={currentEntityId}
        title={`${version.parameter_name} ${version.qid}`}
      />
    </div>
  );
}
