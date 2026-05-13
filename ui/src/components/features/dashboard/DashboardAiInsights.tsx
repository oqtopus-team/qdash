"use client";

import { useMemo } from "react";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Info, OctagonAlert, Sparkles } from "lucide-react";

import { customInstance } from "@/lib/custom-instance";

type InsightSeverity = "info" | "warning" | "critical";
type InsightConfidence = "low" | "medium" | "high";

interface DashboardInsight {
  title: string;
  severity: InsightSeverity;
  affected_targets: string[];
  category: string;
  evidence: string[];
  recommended_action: string;
  confidence: InsightConfidence;
}

interface DashboardAiInsightsResponse {
  chip_id: string;
  summary: string;
  insights: DashboardInsight[];
  suppressed: {
    routine_pass_count: number;
    reason: string;
  };
}

interface DashboardAiInsightsProps {
  chipId: string;
  selectionMode: "latest" | "best" | "average";
  startAt?: string;
  endAt?: string;
}

function severityClass(severity: InsightSeverity): string {
  switch (severity) {
    case "critical":
      return "border-error/50 bg-error/5 text-error";
    case "warning":
      return "border-warning/50 bg-warning/5 text-warning";
    default:
      return "border-info/40 bg-info/5 text-info";
  }
}

function SeverityIcon({ severity }: { severity: InsightSeverity }) {
  if (severity === "critical") return <OctagonAlert className="h-4 w-4" />;
  if (severity === "warning") return <AlertTriangle className="h-4 w-4" />;
  return <Info className="h-4 w-4" />;
}

async function getDashboardAiInsights({
  chipId,
  selectionMode,
  startAt,
  endAt,
}: DashboardAiInsightsProps) {
  const response = await customInstance<DashboardAiInsightsResponse>({
    url: `/dashboard/chips/${chipId}/ai-insights`,
    method: "GET",
    params: {
      selection_mode: selectionMode,
      start_at: startAt,
      end_at: endAt,
      latest_only: true,
    },
  });
  return response.data;
}

export function DashboardAiInsights({
  chipId,
  selectionMode,
  startAt,
  endAt,
}: DashboardAiInsightsProps) {
  const queryKey = useMemo(
    () => ["dashboard-ai-insights", chipId, selectionMode, startAt, endAt],
    [chipId, selectionMode, startAt, endAt],
  );
  const { data, isLoading, isError } = useQuery({
    queryKey,
    queryFn: () => getDashboardAiInsights({ chipId, selectionMode, startAt, endAt }),
    enabled: Boolean(chipId),
    staleTime: 30_000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-base-content/60">
        <span className="loading loading-spinner loading-xs" />
        Generating dashboard insights...
      </div>
    );
  }

  if (isError) {
    return <div className="text-sm text-error">Failed to load dashboard insights.</div>;
  }

  if (!data || data.insights.length === 0) {
    return (
      <div className="space-y-2">
        <div className="flex items-center gap-2 text-sm text-base-content/70">
          <Sparkles className="h-4 w-4" />
          {data?.summary ?? "No dashboard insights are available yet."}
        </div>
        {data?.suppressed.routine_pass_count ? (
          <p className="text-xs text-base-content/50">
            Suppressed {data.suppressed.routine_pass_count} routine pass note
            {data.suppressed.routine_pass_count > 1 ? "s" : ""}.
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm text-base-content/70">
        <Sparkles className="h-4 w-4" />
        <span>{data.summary}</span>
      </div>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        {data.insights.map((insight) => (
          <article
            key={`${insight.category}-${insight.title}`}
            className={`rounded-lg border p-3 space-y-2 ${severityClass(insight.severity)}`}
          >
            <div className="flex items-start gap-2">
              <span className="mt-0.5 flex-shrink-0">
                <SeverityIcon severity={insight.severity} />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <h4 className="text-sm font-semibold text-base-content">{insight.title}</h4>
                  <span className="badge badge-outline badge-xs">{insight.confidence}</span>
                </div>
                {insight.affected_targets.length > 0 && (
                  <p className="text-xs text-base-content/60 mt-0.5">
                    {insight.affected_targets.join(", ")}
                  </p>
                )}
              </div>
            </div>
            <ul className="space-y-1">
              {insight.evidence.slice(0, 2).map((item) => (
                <li key={item} className="text-xs text-base-content/75 break-words">
                  {item}
                </li>
              ))}
            </ul>
            <p className="text-xs font-medium text-base-content">{insight.recommended_action}</p>
          </article>
        ))}
      </div>
      {data.suppressed.routine_pass_count > 0 && (
        <p className="text-xs text-base-content/50">
          Suppressed {data.suppressed.routine_pass_count} routine pass note
          {data.suppressed.routine_pass_count > 1 ? "s" : ""}.
        </p>
      )}
    </div>
  );
}
