"use client";

import React, { useState } from "react";

import { useGetQubitMetricHistory } from "@/client/metrics/metrics";
import { TaskFigure } from "@/components/charts/TaskFigure";

interface MetricHistoryItem {
  value: number | null;
  execution_id: string;
  task_id: string | null;
  timestamp: string;
  calibrated_at: string | null;
}

interface QubitMetricHistoryModalProps {
  chipId: string;
  qid: string;
  metricName: string;
  metricUnit: string;
}

// Helper function to format metric value based on unit
function formatMetricValue(
  value: number | null,
  unit: string,
  precision: number = 2,
): string {
  if (value === null || value === undefined) return "N/A";
  // For percentage units, multiply by 100 to display correctly
  const displayValue = unit === "%" ? value * 100 : value;
  return displayValue.toFixed(precision);
}

export function QubitMetricHistoryModal({
  chipId,
  qid,
  metricName,
  metricUnit,
}: QubitMetricHistoryModalProps) {
  const [selectedIndex, setSelectedIndex] = useState(0);

  const { data, isLoading, isError } = useGetQubitMetricHistory(
    chipId,
    qid,
    { metric: metricName, limit: 20, within_days: 30 },
    {
      query: {
        staleTime: 30000, // Cache for 30 seconds
        gcTime: 60000, // Keep in cache for 1 minute
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

  const selectedItem = history[selectedIndex];

  return (
    <div className="flex flex-col lg:flex-row gap-3 sm:gap-4 h-full">
      {/* Image Display - shown first on mobile (top), second on desktop (right) */}
      <div className="order-1 lg:order-2 lg:w-2/3 flex flex-col">
        <div className="flex items-center justify-between mb-2 sm:mb-3">
          <h3 className="text-base sm:text-lg font-bold">Calibration Result</h3>
          <div className="text-xs sm:text-sm text-base-content/60">
            {selectedIndex + 1} / {history.length}
          </div>
        </div>

        {/* Navigation Arrows */}
        <div className="flex gap-2 mb-2 sm:mb-3">
          <button
            className="btn btn-xs sm:btn-sm btn-ghost"
            disabled={selectedIndex === 0}
            onClick={() => setSelectedIndex((prev) => Math.max(0, prev - 1))}
          >
            ← Newer
          </button>
          <button
            className="btn btn-xs sm:btn-sm btn-ghost"
            disabled={selectedIndex === history.length - 1}
            onClick={() =>
              setSelectedIndex((prev) => Math.min(history.length - 1, prev + 1))
            }
          >
            Older →
          </button>
        </div>

        {/* Image Display */}
        <div className="flex-1 bg-base-200 rounded-lg p-2 sm:p-4 overflow-auto min-h-[200px] sm:min-h-[400px]">
          {selectedItem.task_id ? (
            <TaskFigure
              taskId={selectedItem.task_id}
              qid={qid}
              className="w-full h-auto"
            />
          ) : (
            <div className="alert alert-warning text-sm">
              <svg
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
                className="stroke-current shrink-0 w-5 h-5 sm:w-6 sm:h-6"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                />
              </svg>
              <span>No figure available</span>
            </div>
          )}
        </div>

        {/* Metadata - hidden on mobile */}
        <div className="hidden sm:block mt-3 text-xs text-base-content/60 space-y-1 bg-base-200 p-3 rounded-lg">
          <div className="flex items-center gap-2">
            <span className="font-semibold">Execution ID:</span>
            <span className="font-mono truncate">
              {selectedItem.execution_id}
            </span>
          </div>
          {selectedItem.task_id && (
            <div className="flex items-center gap-2">
              <span className="font-semibold">Task ID:</span>
              <span className="font-mono truncate">{selectedItem.task_id}</span>
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

      {/* History List - shown second on mobile (bottom), first on desktop (left) */}
      <div className="order-2 lg:order-1 lg:w-1/3 flex flex-col">
        <h3 className="text-base sm:text-lg font-bold mb-2 sm:mb-3">History</h3>
        <div className="flex-1 overflow-y-auto max-h-[180px] sm:max-h-[500px]">
          {/* Mobile: horizontal scroll list */}
          <div className="flex gap-2 overflow-x-auto pb-2 sm:hidden">
            {history.map((item, idx) => (
              <button
                key={item.execution_id}
                onClick={() => setSelectedIndex(idx)}
                className={`flex-shrink-0 text-left p-2 rounded-lg transition-all min-w-[100px] ${
                  idx === selectedIndex
                    ? "bg-primary text-primary-content"
                    : "bg-base-200 hover:bg-base-300"
                }`}
              >
                <div className="font-bold text-sm">
                  {formatMetricValue(item.value, metricUnit, 2)} {metricUnit}
                </div>
                <div className="text-[0.65rem] opacity-70">
                  {new Date(item.timestamp).toLocaleString("ja-JP", {
                    timeZone: "Asia/Tokyo",
                    month: "numeric",
                    day: "numeric",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </div>
                {idx === 0 && (
                  <span className="badge badge-xs badge-success mt-0.5">
                    Latest
                  </span>
                )}
              </button>
            ))}
          </div>
          {/* Mobile: selected item details below cards */}
          {selectedItem && (
            <div className="sm:hidden mt-2 p-2 bg-base-200 rounded-lg text-xs space-y-1">
              <div className="flex justify-between">
                <span className="opacity-70">Execution ID:</span>
                <span className="font-mono truncate max-w-[180px]">
                  {selectedItem.execution_id}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="opacity-70">Timestamp:</span>
                <span>
                  {new Date(selectedItem.timestamp).toLocaleString("ja-JP", {
                    timeZone: "Asia/Tokyo",
                  })}
                </span>
              </div>
            </div>
          )}
          {/* Desktop: vertical list */}
          <div className="hidden sm:flex flex-col gap-2">
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
                      {formatMetricValue(item.value, metricUnit, 4)}{" "}
                      {metricUnit}
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
      </div>
    </div>
  );
}
