"use client";

import { useState, useMemo } from "react";
import { ParameterSelector } from "@/app/components/ParameterSelector";
import { TagSelector } from "@/app/components/TagSelector";
import { useTimeRange } from "@/shared/hooks/useTimeRange";
import { useQubitCorrelation } from "../hooks/useQubitCorrelation";
import { useQubitParameters } from "../hooks/useQubitTimeseries";
import { PlotCard } from "@/shared/components/PlotCard";
import { StatisticsCards } from "@/shared/components/StatisticsCards";
import { CorrelationDataTable } from "./CorrelationDataTable";
import { ErrorCard } from "@/shared/components/ErrorCard";
import { ParameterKey, TagKey } from "../types";

interface QubitParameterCorrelationViewProps {
  chipId: string;
  qubitId: string;
}

export function QubitParameterCorrelationView({ chipId, qubitId }: QubitParameterCorrelationViewProps) {
  const [xAxis, setXAxis] = useState<ParameterKey>("t1");
  const [yAxis, setYAxis] = useState<ParameterKey>("t2_echo");
  const [selectedTag, setSelectedTag] = useState<TagKey>("daily");
  
  // Time range management (30 days by default for correlation analysis)
  const { timeRange } = useTimeRange({ initialDays: 30 });

  // Fetch parameters and tags
  const { parameters, tags, isLoading: isLoadingMeta, error: metaError } = useQubitParameters();

  // Fetch correlation data
  const {
    correlationData,
    plotData,
    statistics,
    isLoading,
    error,
  } = useQubitCorrelation({
    chipId,
    qubitId,
    xParameter: xAxis,
    yParameter: yAxis,
    tag: selectedTag,
    timeRange,
  });


  // Plot layout configuration
  const layout = useMemo(() => ({
    title: "",
    autosize: true,
    xaxis: {
      title: {
        text: `${xAxis} ${
          correlationData?.[0]?.xUnit ? `(${correlationData[0].xUnit})` : ""
        }`,
        font: { size: 14 },
      },
      autorange: true,
      rangemode: "normal",
      type: "linear",
      gridcolor: "rgba(128, 128, 128, 0.2)",
      zerolinecolor: "rgba(128, 128, 128, 0.2)",
      showgrid: true,
      zeroline: true,
      showline: true,
      exponentformat: "e",
    },
    yaxis: {
      title: {
        text: `${yAxis} ${
          correlationData?.[0]?.yUnit ? `(${correlationData[0].yUnit})` : ""
        }`,
        font: { size: 14 },
      },
      autorange: true,
      rangemode: "normal",
      type: "linear",
      gridcolor: "rgba(128, 128, 128, 0.2)",
      zerolinecolor: "rgba(128, 128, 128, 0.2)",
      showgrid: true,
      zeroline: true,
      showline: true,
      exponentformat: "e",
    },
    plot_bgcolor: "rgba(0,0,0,0)",
    paper_bgcolor: "rgba(0,0,0,0)",
    hovermode: "closest",
    margin: { t: 10, r: 140, b: 60, l: 80 },
    showlegend: false,
  }), [xAxis, yAxis, correlationData]);

  // Error handling
  if (metaError || error) {
    return (
      <ErrorCard
        message={metaError?.message || error?.message || "Failed to load correlation data"}
        onRetry={() => window.location.reload()}
        title="Correlation Data Error"
      />
    );
  }

  const isSameParameter = xAxis === yAxis;

  return (
    <div className="space-y-8">
      {/* Parameter Selection Card */}
      <div className="card bg-base-100 shadow-xl rounded-xl p-8 border border-base-300">
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
            <circle cx="15" cy="10" r="1"></circle>
            <circle cx="12" cy="15" r="1"></circle>
            <circle cx="8" cy="9" r="1"></circle>
          </svg>
          Parameter Correlation - Qubit {qubitId}
        </h2>
        
        <div className="grid grid-cols-3 gap-12">
          <ParameterSelector
            label="X-Axis Parameter"
            parameters={parameters}
            selectedParameter={xAxis}
            onParameterSelect={(param) => setXAxis(param as ParameterKey)}
            disabled={isLoadingMeta}
          />
          <ParameterSelector
            label="Y-Axis Parameter"
            parameters={parameters}
            selectedParameter={yAxis}
            onParameterSelect={(param) => setYAxis(param as ParameterKey)}
            disabled={isLoadingMeta}
          />
          <TagSelector
            tags={tags}
            selectedTag={selectedTag}
            onTagSelect={(tag) => setSelectedTag(tag as TagKey)}
            disabled={isLoadingMeta}
          />
        </div>
        
        {isSameParameter && (
          <div className="alert alert-warning mt-4" role="alert">
            <svg 
              xmlns="http://www.w3.org/2000/svg" 
              className="stroke-current shrink-0 h-6 w-6" 
              fill="none" 
              viewBox="0 0 24 24"
              aria-hidden="true"
            >
              <path 
                strokeLinecap="round" 
                strokeLinejoin="round" 
                strokeWidth="2" 
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L3.732 16.5c-.77.833.192 2.5 1.732 2.5z" 
              />
            </svg>
            <span>Select different parameters for X and Y axes to see meaningful correlation</span>
          </div>
        )}
      </div>

      {/* Plot Area */}
      <PlotCard
        title="Parameter Correlation Plot"
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
            <circle cx="15" cy="10" r="1"></circle>
            <circle cx="12" cy="15" r="1"></circle>
            <circle cx="8" cy="9" r="1"></circle>
          </svg>
        }
        isLoading={isLoading}
        hasData={!isSameParameter && plotData.length > 0}
        emptyStateMessage={
          isSameParameter 
            ? "Select different parameters for X and Y axes"
            : "No correlation data available for selected parameters"
        }
        plotData={plotData}
        layout={layout}
        config={{
          toImageButtonOptions: {
            format: "svg",
            filename: `qubit_${qubitId}_correlation`,
            height: 600,
            width: 800,
            scale: 2,
          },
        }}
      />

      {/* Statistics Cards */}
      {statistics && !isSameParameter && (
        <StatisticsCards
          statistics={statistics}
          xParameter={xAxis}
          yParameter={yAxis}
          xUnit={correlationData?.[0]?.xUnit}
          yUnit={correlationData?.[0]?.yUnit}
        />
      )}

      {/* Data Table */}
      {correlationData && correlationData.length > 0 && !isSameParameter && (
        <CorrelationDataTable
          data={correlationData}
          qubitId={qubitId}
          xParameter={xAxis}
          yParameter={yAxis}
        />
      )}
    </div>
  );
}