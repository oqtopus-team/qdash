"use client";

import { useGetQubitMetricHistory } from "@/client/metrics/metrics";

import type { MetricHistoryItem } from "./MetricHistoryView";
import { TargetMetricHistoryModal } from "./TargetMetricHistoryModal";

interface QubitMetricHistoryModalProps {
  chipId: string;
  qid: string;
  metricName: string;
  metricUnit: string;
  startAt?: string | null;
  endAt?: string | null;
}

/** History of a qubit metric, with the selected execution's task details. */
export function QubitMetricHistoryModal({
  chipId,
  qid,
  metricName,
  metricUnit,
  startAt,
  endAt,
}: QubitMetricHistoryModalProps) {
  const { data, isLoading, isError } = useGetQubitMetricHistory(
    chipId,
    qid,
    { metric: metricName, limit: 100, within_days: 365 },
    {
      query: {
        staleTime: 30000,
        gcTime: 60000,
      },
    },
  );

  return (
    <TargetMetricHistoryModal
      chipId={chipId}
      targetId={qid}
      targetKind="qubit"
      metricName={metricName}
      metricUnit={metricUnit}
      startAt={startAt}
      endAt={endAt}
      query={{
        history: data?.data?.history as MetricHistoryItem[] | undefined,
        isLoading,
        isError,
      }}
    />
  );
}
