"use client";

import { useMemo, useEffect } from "react";

import type { ParameterKey, TagKey } from "@/shared/types/analysis";
import type { Layout } from "plotly.js";

import { ChipSelector } from "@/app/components/ChipSelector";
import { DateTimePicker } from "@/app/components/DateTimePicker";
import { ParameterSelector } from "@/app/components/ParameterSelector";
import { TagSelector } from "@/app/components/TagSelector";
import { useAnalysisUrlState } from "@/app/hooks/useUrlState";
import { useFetchTimeseriesTaskResultByTagAndParameter } from "@/client/chip/chip";
import { useListChips } from "@/client/chip/chip";
import { useFetchAllParameters } from "@/client/parameter/parameter";
import { DataTable } from "@/shared/components/DataTable";
import { PlotCard } from "@/shared/components/PlotCard";
import { useCSVExport } from "@/shared/hooks/useCSVExport";
import { useTimeRange } from "@/shared/hooks/useTimeRange";
import { ErrorCard } from "@/shared/components/ErrorCard";
import { useListAllTag } from "@/client/tag/tag";

export function TimeSeriesView() {
  // URL state management
  const {
    selectedChip,
    selectedParameter,
    selectedTag,
    setSelectedChip,
    setSelectedParameter,
    setSelectedTag,
    isInitialized,
  } = useAnalysisUrlState();
  // Time range management with manual refresh
  const {
    timeRange,
    updateStartAt,
    updateEndAt,
    toggleStartAtLock,
    toggleEndAtLock,
    refreshTimeRange,
    getLockStatusDescription,
  } = useTimeRange({ initialDays: 7 });

  // Fetch chips data for default selection
  const { data: chipsResponse } = useListChips();

  // Fetch parameters and tags
  const { data: parametersResponse, isLoading: isLoadingParameters } =
    useFetchAllParameters();
  const { data: tagsResponse, isLoading: isLoadingTags } = useListAllTag();

  // Set default chip when URL is initialized and no chip is selected
  useEffect(() => {
    if (
      isInitialized &&
      !selectedChip &&
      chipsResponse?.data &&
      chipsResponse.data.length > 0
    ) {
      // Sort chips by installation date and select the most recent one
      const sortedChips = [...chipsResponse.data].sort((a, b) => {
        const dateA = a.installed_at ? new Date(a.installed_at).getTime() : 0;
        const dateB = b.installed_at ? new Date(b.installed_at).getTime() : 0;
        return dateB - dateA;
      });
      setSelectedChip(sortedChips[0].chip_id);
    }
  }, [isInitialized, selectedChip, chipsResponse, setSelectedChip]);

  // Fetch time series data directly (Analysis page doesn't have qubitId)
  const {
    data: timeseriesResponse,
    isLoading: isLoadingTimeseries,
    error,
    refetch,
  } = useFetchTimeseriesTaskResultByTagAndParameter(
    selectedChip,
    selectedParameter as ParameterKey,
    {
      tag: selectedTag as TagKey,
      start_at: timeRange.startAt,
      end_at: timeRange.endAt,
    },
    {
      query: {
        enabled: Boolean(selectedChip && selectedParameter && selectedTag),
        staleTime: 30000, // Keep data fresh for 30 seconds
      },
    },
  );

  // Process data using shared processing logic
  const { tableData, plotData, metadata } = useMemo(() => {
    if (!timeseriesResponse?.data?.data) {
      return {
        tableData: [],
        plotData: [],
        metadata: { unit: "a.u.", description: "" },
      };
    }

    // Table data processing
    const tableRows: any[] = [];
    Object.entries(timeseriesResponse.data.data).forEach(
      ([qid, dataPoints]) => {
        if (Array.isArray(dataPoints)) {
          dataPoints.forEach((point: any) => {
            tableRows.push({
              qid,
              time: point.calibrated_at || "",
              value: point.value || 0,
              error: point.error,
              unit: point.unit || "a.u.",
            });
          });
        }
      },
    );

    // Sort by QID and time
    const sortedTableData = tableRows.sort((a, b) => {
      const qidCompare = parseInt(a.qid) - parseInt(b.qid);
      if (qidCompare !== 0) return qidCompare;
      return a.time.localeCompare(b.time);
    });

    // Plot data processing
    const qidData: Record<
      string,
      { x: string[]; y: number[]; error: number[] }
    > = {};

    Object.entries(timeseriesResponse.data.data).forEach(
      ([qid, dataPoints]) => {
        if (Array.isArray(dataPoints)) {
          qidData[qid] = {
            x: dataPoints.map((point: any) => point.calibrated_at || ""),
            y: dataPoints.map((point: any) => {
              const value = point.value;
              if (typeof value === "number") return value;
              if (typeof value === "string") return Number(value) || 0;
              return 0;
            }),
            error: dataPoints.map((point: any) => point.error || 0),
          };
        }
      },
    );

    // Sort QIDs numerically and create traces
    const sortedQids = Object.keys(qidData).sort(
      (a, b) => parseInt(a) - parseInt(b),
    );
    const traces = sortedQids.map((qid) => ({
      x: qidData[qid].x,
      y: qidData[qid].y,
      error_y: {
        type: "data" as const,
        array: qidData[qid].error as Plotly.Datum[],
        visible: true,
      },
      type: "scatter" as const,
      mode: "lines+markers" as const,
      name: `QID: ${qid}`,
      line: { shape: "linear" as const, width: 2 },
      marker: { size: 8, symbol: "circle" },
      hovertemplate:
        "Time: %{x}<br>Value: %{y:.8f}" +
        (qidData[qid].error[0] ? "<br>Error: ±%{error_y.array:.8f}" : "") +
        "<br>QID: " +
        qid +
        "<extra></extra>",
    }));

    // Extract metadata
    const firstEntry = Object.entries(timeseriesResponse.data.data)[0];
    let metaInfo = { unit: "a.u.", description: "" };
    if (
      firstEntry &&
      Array.isArray(firstEntry[1]) &&
      firstEntry[1].length > 0
    ) {
      const firstPoint = firstEntry[1][0] as any;
      metaInfo = {
        unit: firstPoint.unit || "a.u.",
        description: firstPoint.description || "",
      };
    }

    return {
      tableData: sortedTableData,
      plotData: traces,
      metadata: metaInfo,
    };
  }, [timeseriesResponse]);

  // CSV export functionality
  const { exportTimeSeriesCSV } = useCSVExport();

  // Plot layout configuration
  const layout = useMemo<Partial<Layout>>(
    () => ({
      title: {
        text: `${selectedParameter} Time Series by QID`,
        font: { size: 24 },
      },
      xaxis: {
        title: "Time",
        type: "date",
        tickformat: "%Y-%m-%d %H:%M",
        gridcolor: "#eee",
        zeroline: false,
      },
      yaxis: {
        title: `${metadata.description} [${metadata.unit}]`,
        type: "linear",
        gridcolor: "#eee",
        zeroline: false,
        exponentformat: "e" as const,
      },
      showlegend: true,
      legend: {
        x: 1.05,
        y: 1,
        xanchor: "left",
        yanchor: "top",
        bgcolor: "rgba(255, 255, 255, 0.8)",
      },
      autosize: true,
      margin: { l: 80, r: 150, t: 100, b: 80 },
      plot_bgcolor: "white",
      paper_bgcolor: "white",
      hovermode: "closest",
    }),
    [selectedParameter, metadata],
  );

  const parameters = parametersResponse?.data?.parameters || [];
  const tags = tagsResponse?.data?.tags || [];

  // Handle CSV download
  const handleDownloadCSV = () => {
    exportTimeSeriesCSV(
      tableData,
      selectedParameter as ParameterKey,
      selectedChip,
      selectedTag as TagKey,
    );
  };

  // Manual refresh handler
  const handleRefresh = () => {
    refreshTimeRange();
    refetch();
  };

  // Error handling
  if (error) {
    return (
      <ErrorCard
        title="Time Series Data Error"
        message={error.message || "Failed to load time series data"}
        onRetry={() => window.location.reload()}
      />
    );
  }

  // Table columns definition
  const tableColumns = [
    { key: "qid", label: "QID", sortable: true, className: "text-left" },
    { key: "time", label: "Time", sortable: true, className: "text-left" },
    {
      key: "value",
      label: "Value",
      sortable: false,
      className: "text-center",
      render: (value: any) =>
        typeof value === "number" ? value.toFixed(4) : String(value),
    },
    {
      key: "error",
      label: "Error",
      sortable: false,
      className: "text-center",
      render: (value: any) =>
        value !== undefined ? `±${value.toFixed(4)}` : "-",
    },
    { key: "unit", label: "Unit", sortable: false, className: "text-center" },
  ];

  return (
    <div className="grid grid-cols-3 gap-8">
      {/* Parameter Selection Card */}
      <div className="col-span-3 card bg-base-100 shadow-xl rounded-xl p-8 border border-base-300">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-xl font-semibold flex items-center gap-2">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="w-5 h-5"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M3 3v18h18"></path>
              <path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"></path>
            </svg>
            Parameter Selection
          </h2>
          <button
            onClick={handleRefresh}
            disabled={
              isLoadingTimeseries || isLoadingParameters || isLoadingTags
            }
            className="btn btn-sm btn-outline gap-2"
            title="Refresh data and time range"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="w-4 h-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8" />
              <path d="M21 3v5h-5" />
              <path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16" />
              <path d="M3 21v-5h5" />
            </svg>
            Refresh
          </button>
        </div>
        <div className="grid grid-cols-3 gap-12">
          <ChipSelector
            selectedChip={selectedChip}
            onChipSelect={setSelectedChip}
          />
          <ParameterSelector
            label="Parameter"
            parameters={parameters.map((p) => p.name)}
            selectedParameter={selectedParameter}
            onParameterSelect={setSelectedParameter}
            disabled={isLoadingParameters}
          />
          <TagSelector
            tags={tags}
            selectedTag={selectedTag}
            onTagSelect={setSelectedTag}
            disabled={isLoadingTags}
          />
        </div>
        <div className="mt-4">
          <span className="text-sm font-medium mb-2 block">Time Range</span>
          <div className="grid grid-cols-2 gap-4">
            <div className="flex items-start gap-2">
              <div className="flex-1">
                <DateTimePicker
                  label="From"
                  value={timeRange.startAt}
                  onChange={updateStartAt}
                  disabled={isLoadingTags}
                />
              </div>
              <button
                className={`btn btn-sm mt-8 gap-2 ${
                  timeRange.isStartAtLocked ? "btn-primary" : "btn-ghost"
                }`}
                onClick={toggleStartAtLock}
                title={
                  timeRange.isStartAtLocked
                    ? "Unlock start time"
                    : "Lock start time"
                }
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="w-4 h-4"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  {timeRange.isStartAtLocked ? (
                    <>
                      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                    </>
                  ) : (
                    <>
                      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                      <path d="M7 11V7a5 5 0 0 1 9.9-1" />
                    </>
                  )}
                </svg>
                {timeRange.isStartAtLocked ? "Fixed" : "Auto"}
              </button>
            </div>
            <div className="flex items-start gap-2">
              <div className="flex-1">
                <DateTimePicker
                  label="To"
                  value={timeRange.endAt}
                  onChange={updateEndAt}
                  disabled={isLoadingTags}
                />
              </div>
              <button
                className={`btn btn-sm mt-8 gap-2 ${
                  timeRange.isEndAtLocked ? "btn-primary" : "btn-ghost"
                }`}
                onClick={toggleEndAtLock}
                title={
                  timeRange.isEndAtLocked ? "Unlock end time" : "Lock end time"
                }
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  className="w-4 h-4"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                >
                  {timeRange.isEndAtLocked ? (
                    <>
                      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
                    </>
                  ) : (
                    <>
                      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                      <path d="M7 11V7a5 5 0 0 1 9.9-1" />
                    </>
                  )}
                </svg>
                {timeRange.isEndAtLocked ? "Fixed" : "Auto"}
              </button>
            </div>
          </div>
          <div className="mt-2 text-xs text-base-content/70 flex items-center gap-1">
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="w-4 h-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="16" x2="12" y2="12" />
              <line x1="12" y1="8" x2="12" y2="8" />
            </svg>
            {getLockStatusDescription()}
          </div>
        </div>
      </div>

      {/* Plot Area */}
      <PlotCard
        title="Time Series Plot"
        icon={
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="w-6 h-6"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <path d="M3 3v18h18"></path>
            <path d="M3 12h18"></path>
            <path d="M12 3v18"></path>
          </svg>
        }
        isLoading={isLoadingTimeseries}
        hasData={Boolean(
          selectedChip &&
            selectedParameter &&
            selectedTag &&
            plotData.length > 0,
        )}
        emptyStateMessage={
          !selectedChip || !selectedParameter || !selectedTag
            ? "Select chip and parameters to visualize data"
            : "No data available for the selected parameters"
        }
        plotData={plotData}
        layout={layout}
        config={{
          toImageButtonOptions: {
            format: "svg",
            filename: "time_series",
            height: 600,
            width: 800,
            scale: 2,
          },
        }}
        className="col-span-3"
      />

      {/* Data Table */}
      <DataTable
        title="Data Table"
        data={tableData}
        columns={tableColumns}
        searchable={true}
        searchPlaceholder="Filter by QID..."
        searchKey="qid"
        pageSize={50}
        actions={
          <button
            className="btn btn-sm btn-outline gap-2"
            onClick={handleDownloadCSV}
            disabled={tableData.length === 0}
            title="Download all data as CSV"
          >
            <svg
              xmlns="http://www.w3.org/2000/svg"
              className="w-4 h-4"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
              <polyline points="7 10 12 15 17 10" />
              <line x1="12" y1="15" x2="12" y2="3" />
            </svg>
            Download CSV
          </button>
        }
        className="col-span-3"
        emptyMessage="Select parameters to view data table"
      />
    </div>
  );
}
