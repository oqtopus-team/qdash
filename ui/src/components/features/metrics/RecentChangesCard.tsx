"use client";

import { useMemo } from "react";

import Link from "next/link";

import {
  Clock,
  TrendingUp,
  TrendingDown,
  Minus,
  GitBranch,
} from "lucide-react";

import { useGetRecentChanges } from "@/client/provenance/provenance";
import { Card } from "@/components/ui/Card";
import { useMetricsConfig } from "@/hooks/useMetricsConfig";
import { formatRelativeTime } from "@/utils/datetime";

interface RecentChangesCardProps {
  limit?: number;
}

function formatValue(value: number | string | null | undefined): string {
  if (value === null || value === undefined) return "-";
  if (typeof value === "number") {
    if (Math.abs(value) < 0.01 || Math.abs(value) > 10000) {
      return value.toExponential(2);
    }
    return value.toFixed(4);
  }
  return String(value);
}

function formatDeltaPercent(percent: number | null | undefined): string {
  if (percent === null || percent === undefined) return "";
  const sign = percent >= 0 ? "+" : "";
  return `${sign}${percent.toFixed(1)}%`;
}

function DeltaIndicator({
  deltaPercent,
}: {
  deltaPercent: number | null | undefined;
}) {
  if (deltaPercent === null || deltaPercent === undefined) {
    return <Minus className="h-3 w-3 text-base-content/40" />;
  }

  const isSignificant = Math.abs(deltaPercent) > 10;

  if (deltaPercent > 0) {
    return (
      <TrendingUp
        className={`h-3 w-3 ${isSignificant ? "text-warning" : "text-success"}`}
      />
    );
  } else if (deltaPercent < 0) {
    return (
      <TrendingDown
        className={`h-3 w-3 ${isSignificant ? "text-warning" : "text-error"}`}
      />
    );
  }
  return <Minus className="h-3 w-3 text-base-content/40" />;
}

export function RecentChangesCard({ limit = 10 }: RecentChangesCardProps) {
  const { allMetrics, isLoading: isLoadingConfig } = useMetricsConfig();

  // Get parameter names from metrics config
  const parameterNames = useMemo(() => {
    return allMetrics.map((m) => m.key);
  }, [allMetrics]);

  const { data, isLoading, error } = useGetRecentChanges(
    {
      limit,
      within_hours: 24,
      parameter_names: parameterNames.length > 0 ? parameterNames : undefined,
    },
    {
      query: {
        staleTime: 30000,
        enabled: !isLoadingConfig && parameterNames.length > 0,
      },
    },
  );

  const changes = data?.data?.changes || [];

  if (isLoading || isLoadingConfig) {
    return (
      <Card variant="default" padding="md">
        <div className="flex items-center gap-2 mb-3">
          <Clock className="h-4 w-4 text-primary" />
          <h3 className="font-semibold text-sm">Recent Changes (24h)</h3>
        </div>
        <div className="flex justify-center py-4">
          <span className="loading loading-spinner loading-sm"></span>
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card variant="default" padding="md">
        <div className="flex items-center gap-2 mb-3">
          <Clock className="h-4 w-4 text-primary" />
          <h3 className="font-semibold text-sm">Recent Changes (24h)</h3>
        </div>
        <p className="text-xs text-base-content/60">Failed to load changes</p>
      </Card>
    );
  }

  if (changes.length === 0) {
    return (
      <Card variant="default" padding="md">
        <div className="flex items-center gap-2 mb-3">
          <Clock className="h-4 w-4 text-primary" />
          <h3 className="font-semibold text-sm">Recent Changes (24h)</h3>
        </div>
        <p className="text-xs text-base-content/60">
          No parameter changes in the last 24 hours
        </p>
      </Card>
    );
  }

  return (
    <Card variant="default" padding="md">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Clock className="h-4 w-4 text-primary" />
          <h3 className="font-semibold text-sm">Recent Changes (24h)</h3>
          <span className="badge badge-primary badge-xs">{changes.length}</span>
        </div>
        <Link
          href="/provenance"
          className="text-xs text-primary hover:underline"
        >
          View all
        </Link>
      </div>

      <div className="space-y-2 max-h-64 overflow-y-auto">
        {changes.map((change) => {
          const isSignificant =
            change.delta_percent !== null &&
            change.delta_percent !== undefined &&
            Math.abs(change.delta_percent) > 10;

          return (
            <Link
              key={change.entity_id}
              href={`/provenance?parameter=${encodeURIComponent(change.parameter_name)}&qid=${encodeURIComponent(change.qid || "")}&tab=lineage`}
              className={`
                block p-2 rounded-lg border transition-colors hover:bg-base-200
                ${isSignificant ? "border-warning/50 bg-warning/5" : "border-base-300 bg-base-100"}
              `}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2 min-w-0">
                  <DeltaIndicator deltaPercent={change.delta_percent} />
                  <span className="font-medium text-xs truncate">
                    {change.parameter_name}
                  </span>
                  <span className="badge badge-ghost badge-xs">
                    Q{change.qid || "?"}
                  </span>
                </div>
                <div className="flex items-center gap-1 text-[10px] text-base-content/60 flex-shrink-0">
                  <span>{formatRelativeTime(change.valid_from as string)}</span>
                  <GitBranch className="h-2.5 w-2.5" />
                </div>
              </div>

              <div className="flex items-center gap-2 mt-1 text-[10px]">
                <span className="text-base-content/60">
                  {formatValue(change.previous_value)}
                </span>
                <span className="text-base-content/40">→</span>
                <span className="font-mono font-medium">
                  {formatValue(change.value)}
                </span>
                {change.unit && (
                  <span className="text-base-content/50">{change.unit}</span>
                )}
                {change.delta_percent !== null &&
                  change.delta_percent !== undefined && (
                    <span
                      className={`font-medium ${
                        isSignificant
                          ? "text-warning"
                          : change.delta_percent >= 0
                            ? "text-success"
                            : "text-error"
                      }`}
                    >
                      ({formatDeltaPercent(change.delta_percent)})
                    </span>
                  )}
              </div>
            </Link>
          );
        })}
      </div>
    </Card>
  );
}
