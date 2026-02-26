"use client";

import { useMemo } from "react";

import dynamic from "next/dynamic";
import Link from "next/link";
import { X, GitBranch, History, ExternalLink } from "lucide-react";

import {
  useGetParameterHistory,
  useGetProvenanceLineage,
} from "@/client/provenance/provenance";
import { RecalibrationRecommendationsPanel } from "@/components/features/provenance/RecalibrationRecommendationsPanel";
import { formatRelativeTime } from "@/lib/utils/datetime";

const Plot = dynamic(() => import("@/components/charts/Plot"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-[200px]">
      <span className="loading loading-spinner loading-md" />
    </div>
  ),
});

interface InboxDetailPanelProps {
  selection: {
    kind: "change" | "policy" | "trend";
    entityId: string;
    parameterName: string;
    qid: string;
  } | null;
  onClose: () => void;
}

const formatValue = (value: number | string) => {
  if (typeof value === "number") {
    if (value === 0) return "0";
    if (Math.abs(value) < 0.0001 || Math.abs(value) > 10000) {
      return value.toExponential(4);
    }
    return value.toFixed(6);
  }
  return String(value);
};

const kindLabel: Record<string, string> = {
  change: "Recent Change",
  policy: "Policy Violation",
  trend: "Degradation Trend",
};

const kindBadgeClass: Record<string, string> = {
  change: "badge-primary",
  policy: "badge-warning",
  trend: "badge-error",
};

export function InboxDetailPanel({
  selection,
  onClose,
}: InboxDetailPanelProps) {
  const isOpen = !!selection;

  const { data: historyResponse, isLoading: isHistoryLoading } =
    useGetParameterHistory(
      {
        parameter_name: selection?.parameterName ?? "",
        qid: selection?.qid ?? "",
        limit: 50,
      },
      {
        query: {
          staleTime: 30_000,
          enabled: !!selection?.parameterName,
        },
      },
    );

  const { data: lineageResponse, isLoading: isLineageLoading } =
    useGetProvenanceLineage(
      selection?.entityId ?? "",
      { max_depth: 5 },
      {
        query: {
          staleTime: 30_000,
          enabled: !!selection?.entityId,
        },
      },
    );

  const versions = useMemo(
    () => historyResponse?.data?.versions ?? [],
    [historyResponse],
  );

  const chartVersions = useMemo(() => [...versions].reverse(), [versions]);

  const lineageInputs = useMemo(() => {
    const edges = lineageResponse?.data?.edges ?? [];
    const nodes = lineageResponse?.data?.nodes ?? [];
    const usedSourceIds = new Set(
      edges.filter((e) => e.relation_type === "used").map((e) => e.source_id),
    );
    return nodes.filter(
      (n) => usedSourceIds.has(n.node_id) && n.node_type === "entity",
    );
  }, [lineageResponse]);

  const currentVersion = versions[0];

  return (
    <>
      {/* Overlay */}
      {isOpen && (
        <div className="fixed inset-0 bg-black/30 z-40" onClick={onClose} />
      )}

      {/* Panel */}
      <div
        className={`fixed right-0 top-0 h-full z-50 w-full sm:w-96 lg:w-[28rem] bg-base-100 shadow-xl flex flex-col transform transition-transform duration-300 ${
          isOpen ? "translate-x-0" : "translate-x-full"
        }`}
      >
        {selection && (
          <>
            {/* Header */}
            <div className="flex items-start justify-between gap-2 p-4 border-b border-base-300">
              <div className="min-w-0">
                <h2 className="text-lg font-semibold truncate">
                  {selection.parameterName}
                </h2>
                <div className="flex items-center gap-2 mt-1">
                  <span className="font-mono text-xs text-base-content/70">
                    {selection.qid || "-"}
                  </span>
                  <span
                    className={`badge badge-xs ${kindBadgeClass[selection.kind]}`}
                  >
                    {kindLabel[selection.kind]}
                  </span>
                </div>
                {currentVersion && (
                  <div className="text-sm mt-1 text-base-content/70">
                    Current:{" "}
                    <span className="font-mono font-medium text-base-content">
                      {formatValue(currentVersion.value)}{" "}
                      {currentVersion.unit || ""}
                    </span>
                  </div>
                )}
              </div>
              <button
                className="btn btn-sm btn-ghost btn-square"
                onClick={onClose}
              >
                <X className="h-4 w-4" />
              </button>
            </div>

            {/* Scrollable content */}
            <div className="flex-1 overflow-y-auto p-4 space-y-5">
              {/* Time-Series Chart */}
              <section>
                <h3 className="text-sm font-semibold mb-2">
                  Version History Chart
                </h3>
                {isHistoryLoading && (
                  <div className="flex items-center justify-center h-[200px]">
                    <span className="loading loading-spinner loading-md" />
                  </div>
                )}
                {!isHistoryLoading && chartVersions.length >= 2 && (
                  <div className="h-[200px] rounded-lg bg-base-200/50 p-1">
                    <Plot
                      data={[
                        {
                          x: chartVersions.map((v) =>
                            v.valid_from
                              ? new Date(v.valid_from as string).toISOString()
                              : "",
                          ),
                          y: chartVersions.map((v) =>
                            typeof v.value === "number" ? v.value : 0,
                          ),
                          type: "scatter" as const,
                          mode: "lines+markers" as const,
                          marker: { size: 5, color: "#6366f1" },
                          line: { width: 1.5, color: "#6366f1" },
                        },
                      ]}
                      layout={{
                        autosize: true,
                        margin: { l: 50, r: 10, t: 10, b: 40 },
                        paper_bgcolor: "transparent",
                        plot_bgcolor: "transparent",
                        xaxis: {
                          type: "date",
                          showgrid: false,
                          tickfont: { size: 9 },
                        },
                        yaxis: {
                          showgrid: true,
                          gridcolor: "rgba(128,128,128,0.15)",
                          tickfont: { size: 9 },
                        },
                      }}
                      config={{
                        displaylogo: false,
                        responsive: true,
                        displayModeBar: false,
                      }}
                      style={{ width: "100%", height: "100%" }}
                      useResizeHandler
                    />
                  </div>
                )}
                {!isHistoryLoading && chartVersions.length < 2 && (
                  <div className="text-center py-6 text-base-content/50 text-sm">
                    Not enough data points for chart.
                  </div>
                )}
              </section>

              {/* Version History List */}
              <section>
                <h3 className="text-sm font-semibold mb-2">Version History</h3>
                {isHistoryLoading && (
                  <div className="flex justify-center py-4">
                    <span className="loading loading-spinner loading-sm" />
                  </div>
                )}
                {!isHistoryLoading && versions.length === 0 && (
                  <div className="text-center py-4 text-base-content/50 text-sm">
                    No versions found.
                  </div>
                )}
                {!isHistoryLoading && versions.length > 0 && (
                  <div className="space-y-1 max-h-60 overflow-y-auto">
                    {versions.map((v) => {
                      const isSelected = v.entity_id === selection.entityId;
                      return (
                        <div
                          key={v.entity_id}
                          className={`flex items-center justify-between gap-2 px-2 py-1.5 rounded text-sm ${
                            isSelected
                              ? "bg-primary/10 border border-primary/30"
                              : "hover:bg-base-200"
                          }`}
                        >
                          <div className="min-w-0">
                            <span className="font-mono text-xs font-semibold">
                              v{v.version}
                            </span>
                            <span className="ml-2 font-mono text-xs">
                              {formatValue(v.value)}
                            </span>
                            {v.task_name && (
                              <span className="ml-2 text-xs text-base-content/60 truncate">
                                {v.task_name}
                              </span>
                            )}
                          </div>
                          <span className="text-xs text-base-content/50 whitespace-nowrap">
                            {v.valid_from
                              ? formatRelativeTime(v.valid_from as string)
                              : "-"}
                          </span>
                        </div>
                      );
                    })}
                  </div>
                )}
              </section>

              {/* Lineage Inputs */}
              <section>
                <h3 className="text-sm font-semibold mb-2">Lineage Inputs</h3>
                {isLineageLoading && (
                  <div className="flex justify-center py-4">
                    <span className="loading loading-spinner loading-sm" />
                  </div>
                )}
                {!isLineageLoading && lineageInputs.length === 0 && (
                  <div className="text-center py-4 text-base-content/50 text-sm">
                    No input parameters found.
                  </div>
                )}
                {!isLineageLoading && lineageInputs.length > 0 && (
                  <div className="space-y-1">
                    {lineageInputs.map((node) => {
                      const e = node.entity;
                      if (!e) return null;
                      return (
                        <div
                          key={node.node_id}
                          className="flex items-center gap-2 px-2 py-1.5 rounded bg-base-200/60 text-sm"
                        >
                          <div
                            className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                              node.depth === 1
                                ? "bg-amber-400"
                                : "bg-emerald-400"
                            }`}
                          />
                          <div className="min-w-0 flex-1">
                            <span className="font-medium text-xs">
                              {e.parameter_name}
                            </span>
                            <span className="ml-1 text-xs text-base-content/60">
                              ({e.qid || "-"})
                            </span>
                            <span className="ml-2 font-mono text-xs text-base-content/70">
                              {formatValue(e.value)}
                            </span>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </section>

              {/* Recommendations */}
              <section>
                <RecalibrationRecommendationsPanel
                  entityId={selection.entityId}
                />
              </section>

              {/* Navigation Links */}
              <section className="pb-4">
                <h3 className="text-sm font-semibold mb-2">Quick Links</h3>
                <div className="flex flex-col gap-1.5">
                  <Link
                    className="btn btn-sm btn-outline gap-2"
                    href={`/provenance?tab=lineage&entity=${encodeURIComponent(
                      selection.entityId,
                    )}`}
                  >
                    <GitBranch className="h-3.5 w-3.5" />
                    Full Lineage View
                    <ExternalLink className="h-3 w-3 ml-auto" />
                  </Link>
                  <Link
                    className="btn btn-sm btn-outline gap-2"
                    href={`/provenance?tab=history&parameter=${encodeURIComponent(
                      selection.parameterName,
                    )}&qid=${encodeURIComponent(selection.qid || "")}`}
                  >
                    <History className="h-3.5 w-3.5" />
                    Full History View
                    <ExternalLink className="h-3 w-3 ml-auto" />
                  </Link>
                </div>
              </section>
            </div>
          </>
        )}
      </div>
    </>
  );
}
