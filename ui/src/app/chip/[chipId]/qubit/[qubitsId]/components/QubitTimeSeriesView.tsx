"use client";

import { useState, useMemo } from "react";
import { Layout } from "plotly.js";
import { ParameterSelector } from "@/app/components/ParameterSelector";
import { TagSelector } from "@/app/components/TagSelector";
import { useTimeRange } from "@/shared/hooks/useTimeRange";
import { useQubitTimeseries, useQubitParameters } from "../hooks/useQubitTimeseries";
import { useCSVExport } from "@/shared/hooks/useCSVExport";
import { TimeRangeControls } from "./TimeRangeControls";
import { PlotCard } from "@/shared/components/PlotCard";
import { DataTable } from "@/shared/components/DataTable";
import { ErrorCard } from "@/shared/components/ErrorCard";
import { ParameterKey, TagKey } from "../types";

interface QubitTimeSeriesViewProps {
  chipId: string;
  qubitId: string;
}

export function QubitTimeSeriesView({ chipId, qubitId }: QubitTimeSeriesViewProps) {
  const [selectedParameter, setSelectedParameter] = useState<ParameterKey>("t1");
  const [selectedTag, setSelectedTag] = useState<TagKey>("daily");
  
  const REFRESH_INTERVAL = 30; // seconds

  // Time range management with auto-refresh
  const {
    timeRange,
    updateStartAt,
    updateEndAt,
    toggleStartAtLock,
    toggleEndAtLock,
  } = useTimeRange({ initialDays: 30, refreshIntervalSeconds: REFRESH_INTERVAL });


  // Fetch parameters and tags
  const { parameters, tags, isLoading: isLoadingMeta, error: metaError } = useQubitParameters();

  // Fetch time series data
  const {
    tableData,
    plotData,
    metadata,
    isLoading,
    error,
    refetch,
  } = useQubitTimeseries({
    chipId,
    qubitId,
    parameter: selectedParameter,
    tag: selectedTag,
    timeRange,
    refreshInterval: REFRESH_INTERVAL * 1000,
  });

  // CSV export functionality
  const { exportTimeSeriesCSV } = useCSVExport();

  const handleDownloadCSV = () => {
    exportTimeSeriesCSV(tableData, selectedParameter, chipId, selectedTag);
  };

  // Plot layout configuration
  const layout = useMemo<Partial<Layout>>(() => ({
    title: {
      text: `${selectedParameter} Time Series - Qubit ${qubitId}`,
      font: { size: 20 },
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
    showlegend: false,
    autosize: true,
    margin: { l: 80, r: 50, t: 60, b: 80 },
    plot_bgcolor: "white",
    paper_bgcolor: "white",
    hovermode: "closest",
  }), [selectedParameter, qubitId, metadata]);

  // Error handling
  if (metaError || error) {
    return (
      <ErrorCard
        message={metaError?.message || error?.message || "Failed to load data"}
        onRetry={() => {
          if (metaError) window.location.reload();
          if (error) refetch();
        }}
        title="Data Loading Error"
      />
    );
  }

  return (
    <div className="space-y-8">
      {/* Parameter Selection Card */}
      <div className="card bg-base-100 shadow-xl rounded-xl p-8 border border-base-300">
        <div className="text-xs text-base-content/70 mb-2">
          Auto refresh every {REFRESH_INTERVAL} seconds
        </div>
        <h2 className="text-xl font-semibold mb-6 flex items-center gap-2">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="w-5 h-5"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M3 3v18h18"></path>
            <path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"></path>
          </svg>
          Time Series Configuration - Qubit {qubitId}
        </h2>
        
        <div className="grid grid-cols-2 gap-12">
          <ParameterSelector
            label="Parameter"
            parameters={parameters}
            selectedParameter={selectedParameter}
            onParameterSelect={(param) => setSelectedParameter(param as ParameterKey)}
            disabled={isLoadingMeta}
          />
          <TagSelector
            tags={tags}
            selectedTag={selectedTag}
            onTagSelect={(tag) => setSelectedTag(tag as TagKey)}
            disabled={isLoadingMeta}
          />
        </div>
        
        <div className="mt-4">
          <TimeRangeControls
            timeRange={timeRange}
            onStartAtChange={updateStartAt}
            onEndAtChange={updateEndAt}
            onToggleStartAtLock={toggleStartAtLock}
            onToggleEndAtLock={toggleEndAtLock}
            disabled={isLoadingMeta}
          />
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
            aria-hidden="true"
          >
            <path d="M3 3v18h18"></path>
            <path d="M3 12h18"></path>
            <path d="M12 3v18"></path>
          </svg>
        }
        isLoading={isLoading}
        hasData={plotData.length > 0}
        emptyStateMessage={`Select parameters to visualize data for Qubit ${qubitId}`}
        plotData={plotData}
        layout={layout}
        config={{
          toImageButtonOptions: {
            format: "svg",
            filename: `qubit_${qubitId}_time_series`,
            height: 600,
            width: 800,
            scale: 2,
          },
        }}
      />

      {/* Data Table */}
      <DataTable
        title="Data Table"
        data={tableData}
        columns={[
          { key: 'time', label: 'Time', sortable: true, className: 'text-left' },
          { 
            key: 'value', 
            label: 'Value', 
            sortable: false, 
            className: 'text-center',
            render: (value: any) => typeof value === 'number' ? value.toFixed(4) : String(value)
          },
          { 
            key: 'error', 
            label: 'Error', 
            sortable: false, 
            className: 'text-center',
            render: (value: any) => value !== undefined ? `±${value.toFixed(4)}` : '-'
          },
          { key: 'unit', label: 'Unit', sortable: false, className: 'text-center' },
        ]}
        searchable={false}
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
        emptyMessage={`No data available for Qubit ${qubitId}`}
      />
    </div>
  );
}