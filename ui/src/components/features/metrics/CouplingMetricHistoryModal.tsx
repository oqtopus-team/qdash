"use client";

import { useMemo, useState } from "react";

import { ArrowRightLeft } from "lucide-react";

import { useGetCouplingMetricHistory } from "@/client/metrics/metrics";

import type { MetricHistoryItem } from "./MetricHistoryView";
import { TargetMetricHistoryModal } from "./TargetMetricHistoryModal";

interface CouplingMetricHistoryModalProps {
  chipId: string;
  couplingId: string;
  metricName: string;
  metricUnit: string;
  startAt?: string | null;
  endAt?: string | null;
}

/** History of a coupling metric, with the selected execution's task details. */
export function CouplingMetricHistoryModal({
  chipId,
  couplingId,
  metricName,
  metricUnit,
  startAt,
  endAt,
}: CouplingMetricHistoryModalProps) {
  // Direction toggle: forward = original coupling ID, reverse = reversed.
  // The shared body clears its selection when the direction changes.
  const [isReversed, setIsReversed] = useState(false);
  const reversedCouplingId = useMemo(() => {
    const parts = couplingId.split("-");
    return parts.length === 2 ? `${parts[1]}-${parts[0]}` : couplingId;
  }, [couplingId]);
  const activeCouplingId = isReversed ? reversedCouplingId : couplingId;

  const { data, isLoading, isError } = useGetCouplingMetricHistory(
    chipId,
    activeCouplingId,
    { metric: metricName, limit: 100, within_days: 365 },
    {
      query: {
        staleTime: 30000,
        gcTime: 60000,
      },
    },
  );

  const directionToggle = (
    <div className="flex items-center gap-2">
      <button
        onClick={() => setIsReversed((prev) => !prev)}
        className={`btn btn-sm ${isReversed ? "btn-secondary" : "btn-outline"}`}
        title={`Switch to ${isReversed ? couplingId : reversedCouplingId}`}
      >
        <ArrowRightLeft data-icon="inline-start" />
        <span className="font-mono text-xs">{activeCouplingId}</span>
      </button>
    </div>
  );

  return (
    <TargetMetricHistoryModal
      chipId={chipId}
      targetId={activeCouplingId}
      targetKind="coupling"
      metricName={metricName}
      metricUnit={metricUnit}
      startAt={startAt}
      endAt={endAt}
      query={{
        history: data?.data?.history as MetricHistoryItem[] | undefined,
        isLoading,
        isError,
      }}
      topContent={directionToggle}
      selectionResetKey={isReversed ? "reverse" : "forward"}
    />
  );
}
