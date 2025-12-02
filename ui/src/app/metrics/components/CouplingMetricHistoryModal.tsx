"use client";

import React, { useState } from "react";

import { TaskFigure } from "@/app/components/TaskFigure";
import { useGetCouplingMetricHistory } from "@/client/metrics/metrics";

interface MetricHistoryItem {
  value: number | null;
  execution_id: string;
  task_id: string | null;
  timestamp: string;
  calibrated_at: string | null;
}

interface CouplingMetricHistoryModalProps {
  chipId: string;
  couplingId: string;
  metricName: string;
  metricUnit: string;
}

export function CouplingMetricHistoryModal({
  chipId,
  couplingId,
  metricName,
  metricUnit,
}: CouplingMetricHistoryModalProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);

  const { data, isLoading, isError } = useGetCouplingMetricHistory(
    chipId,
    couplingId,
    { metric: metricName, limit: 20, within_days: 30 },
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

  const selectedItem = history[selectedIndex];

  return (
    <div className="flex flex-col lg:flex-row gap-4 h-full">
      {/* History List (Left/Top) */}
      <div className="lg:w-1/3 flex flex-col">
        <h3 className="text-lg font-bold mb-3">Calibration History</h3>
        <div className="flex-1 overflow-y-auto space-y-2 max-h-[500px]">
          {history.map((item, idx) => (
            <button
              key={item.execution_id}
              onClick={() => setSelectedIndex(idx)}
              className={`w-full text-left p-3 rounded-lg transition-all ${
                idx === selectedIndex
                  ? "bg-primary text-primary-content"
                  : "bg-base-200 hover:bg-base-300"
              }`}
            >
              <div className="flex justify-between items-start">
                <div>
                  <div className="font-bold text-lg">
                    {item.value?.toFixed(4)} {metricUnit}
                  </div>
                  <div className="text-xs opacity-70 mt-1">
                    {new Date(item.timestamp).toLocaleString("ja-JP", {
                      timeZone: "Asia/Tokyo",
                      month: "short",
                      day: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                    })}
                  </div>
                  {idx === 0 && (
                    <span className="badge badge-sm badge-success mt-1">
                      Latest
                    </span>
                  )}
                </div>
                <div className="text-xs opacity-60">#{idx + 1}</div>
              </div>
            </button>
          ))}
        </div>
      </div>

      {/* Image Display (Right/Bottom) */}
      <div className="lg:w-2/3 flex flex-col">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-lg font-bold">Calibration Result</h3>
          <div className="text-sm text-base-content/60">
            {selectedIndex + 1} / {history.length}
          </div>
        </div>

        {/* Navigation Arrows */}
        <div className="flex gap-2 mb-3">
          <button
            className="btn btn-sm btn-ghost"
            disabled={selectedIndex === 0}
            onClick={() => setSelectedIndex((prev) => Math.max(0, prev - 1))}
          >
            ← Newer
          </button>
          <button
            className="btn btn-sm btn-ghost"
            disabled={selectedIndex === history.length - 1}
            onClick={() =>
              setSelectedIndex((prev) => Math.min(history.length - 1, prev + 1))
            }
          >
            Older →
          </button>
        </div>

        {/* Image Display */}
        <div className="flex-1 bg-base-200 rounded-lg p-4 overflow-auto min-h-[400px]">
          {selectedItem.task_id ? (
            <TaskFigure
              taskId={selectedItem.task_id}
              qid={couplingId}
              className="w-full h-auto"
            />
          ) : (
            <div className="alert alert-warning">
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
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
              <span>No calibration figure available for this execution</span>
            </div>
          )}
        </div>

        {/* Metadata */}
        <div className="mt-3 text-xs text-base-content/60 space-y-1 bg-base-200 p-3 rounded-lg">
          <div className="flex items-center gap-2">
            <span className="font-semibold">Execution ID:</span>
            <span className="font-mono">{selectedItem.execution_id}</span>
          </div>
          {selectedItem.task_id && (
            <div className="flex items-center gap-2">
              <span className="font-semibold">Task ID:</span>
              <span className="font-mono">{selectedItem.task_id}</span>
            </div>
          )}
          <div className="flex items-center gap-2">
            <span className="font-semibold">Timestamp:</span>
            <span>
              {new Date(selectedItem.timestamp).toLocaleString("ja-JP", {
                timeZone: "Asia/Tokyo",
              })}
            </span>
          </div>
          {selectedItem.calibrated_at && (
            <div className="flex items-center gap-2">
              <span className="font-semibold">Calibrated At:</span>
              <span>
                {new Date(selectedItem.calibrated_at).toLocaleString("ja-JP", {
                  timeZone: "Asia/Tokyo",
                })}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
