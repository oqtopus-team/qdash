"use client";

import React, { useState } from "react";

import { useGetQubitMetricHistory } from "@/client/metrics/metrics";

import { ExecutionTasksView } from "./ExecutionTasksView";
import { MetricHistoryView, type MetricHistoryItem } from "./MetricHistoryView";

interface QubitMetricHistoryModalProps {
  chipId: string;
  qid: string;
  metricName: string;
  metricUnit: string;
}

export function QubitMetricHistoryModal({
  chipId,
  qid,
  metricName,
  metricUnit,
}: QubitMetricHistoryModalProps) {
  const [executionFilter, setExecutionFilter] = useState<string | null>(null);

  const { data, isLoading, isError } = useGetQubitMetricHistory(
    chipId,
    qid,
    { metric: metricName, limit: 20, within_days: 30 },
    {
      query: {
        staleTime: 30000,
        gcTime: 60000,
      },
    },
  );

  const history = (data?.data?.history || []) as MetricHistoryItem[];

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96">
        <span className="loading loading-spinner loading-lg"></span>
      </div>
    );
  }

  if (isError || history.length === 0) {
    return (
      <div className="alert alert-info">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
          className="stroke-current shrink-0 w-6 h-6"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
            d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
          />
        </svg>
        <span>No history available for this metric</span>
      </div>
    );
  }

  if (executionFilter) {
    return (
      <ExecutionTasksView
        executionId={executionFilter}
        targetId={qid}
        onBack={() => setExecutionFilter(null)}
      />
    );
  }

  return (
    <MetricHistoryView
      history={history}
      targetId={qid}
      metricName={metricName}
      metricUnit={metricUnit}
      onSelectExecution={setExecutionFilter}
    />
  );
}
