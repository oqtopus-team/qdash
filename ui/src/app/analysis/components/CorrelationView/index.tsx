"use client";

import { useMemo, useState } from "react";
import { useFetchChip } from "@/client/chip/chip";
import { ParameterSelector } from "@/app/components/ParameterSelector";
import { ChipSelector } from "@/app/components/ChipSelector";
import { PlotCard } from "@/shared/components/PlotCard";
import { StatisticsCards } from "@/shared/components/StatisticsCards";
import { DataTable } from "@/shared/components/DataTable";
import { ErrorCard } from "@/shared/components/ErrorCard";
import { useCorrelationData } from "@/shared/hooks/useCorrelationData";
import { ParameterKey } from "@/shared/types/analysis";


export function CorrelationView() {
  const [selectedChip, setSelectedChip] = useState<string>("");
  const [xAxis, setXAxis] = useState<ParameterKey>("");
  const [yAxis, setYAxis] = useState<ParameterKey>("");
  const { data: chipResponse, isLoading: isLoadingChip, error: chipError } = useFetchChip(selectedChip);
  const chipData = useMemo(() => chipResponse?.data, [chipResponse]);

  // Use shared correlation data hook
  const {
    correlationData,
    plotData,
    statistics,
    availableParameters,
    error,
  } = useCorrelationData({
    chipData,
    xParameter: xAxis,
    yParameter: yAxis,
    enabled: Boolean(selectedChip && xAxis && yAxis),
  });

  // Error handling
  if (chipError || error) {
    return (
      <ErrorCard
        title="Correlation Data Error"
        message={chipError?.message || error?.message || "Failed to load correlation data"}
        onRetry={() => window.location.reload()}
      />
    );
  }

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
    margin: { t: 10, r: 140, b: 40, l: 60 },
    showlegend: true,
    legend: {
      orientation: "v",
      yanchor: "top",
      y: 1,
      xanchor: "left",
      x: 1.02,
      bgcolor: "rgba(255,255,255,0.8)",
      bordercolor: "rgba(0,0,0,0.1)",
      borderwidth: 1,
      itemsizing: "constant",
      font: { size: 10 },
    },
  }), [xAxis, yAxis, correlationData]);

  // Table columns definition
  const tableColumns = useMemo(() => {
    const baseColumns = [
      { key: 'qid', label: 'QID', sortable: true, className: 'text-center font-medium' },
      { 
        key: 'x', 
        label: xAxis, 
        sortable: false, 
        className: 'text-center',
        render: (value: number, row: any) => `${value.toFixed(4)} ${row.xUnit}`
      },
      { 
        key: 'y', 
        label: yAxis, 
        sortable: false, 
        className: 'text-center',
        render: (value: number, row: any) => `${value.toFixed(4)} ${row.yUnit}`
      },
    ];

    // Add description columns for non-qid parameters
    if (xAxis !== "qid") {
      baseColumns.push({
        key: 'xDescription',
        label: 'Description (X)',
        sortable: false,
        className: 'text-center',
      });
    }
    if (yAxis !== "qid") {
      baseColumns.push({
        key: 'yDescription',
        label: 'Description (Y)',
        sortable: false,
        className: 'text-center',
      });
    }

    return baseColumns;
  }, [xAxis, yAxis]);

  const isSameParameter = xAxis === yAxis;

  return (
    <div className="grid grid-cols-3 gap-8">
      {/* Parameter Selection Card */}
      <div className="col-span-3 card bg-base-100 shadow-xl rounded-xl p-8 border border-base-300">
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
          >
            <path d="M3 3v18h18"></path>
            <path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"></path>
          </svg>
          Parameter Selection
        </h2>
        <div className="grid grid-cols-3 gap-12">
          <ChipSelector
            selectedChip={selectedChip}
            onChipSelect={setSelectedChip}
          />
          <ParameterSelector
            label="X-Axis Parameter"
            parameters={availableParameters}
            selectedParameter={xAxis}
            onParameterSelect={(param) => setXAxis(param as ParameterKey)}
            description={correlationData?.[0]?.xDescription}
          />
          <ParameterSelector
            label="Y-Axis Parameter"
            parameters={availableParameters}
            selectedParameter={yAxis}
            onParameterSelect={(param) => setYAxis(param as ParameterKey)}
            description={correlationData?.[0]?.yDescription}
          />
        </div>
      </div>

      {/* Warning for same parameter */}
      {isSameParameter && xAxis && yAxis && (
        <div className="col-span-3 alert alert-warning" role="alert">
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
          >
            <path d="M3 3v18h18"></path>
            <circle cx="15" cy="10" r="1"></circle>
            <circle cx="12" cy="15" r="1"></circle>
            <circle cx="8" cy="9" r="1"></circle>
          </svg>
        }
        isLoading={isLoadingChip}
        hasData={!isSameParameter && plotData.length > 0}
        emptyStateMessage={
          isSameParameter 
            ? "Select different parameters for X and Y axes"
            : !selectedChip || !xAxis || !yAxis
            ? "Select chip and parameters to visualize data"
            : "No correlation data available for selected parameters"
        }
        plotData={plotData}
        layout={layout}
        config={{
          toImageButtonOptions: {
            format: "svg",
            filename: "parameter_correlation",
            height: 600,
            width: 800,
            scale: 2,
          },
        }}
        className="col-span-3"
      />

      {/* Statistics Summary */}
      {statistics && !isSameParameter && correlationData.length > 0 && (
        <StatisticsCards
          statistics={statistics}
          xParameter={xAxis}
          yParameter={yAxis}
          xUnit={correlationData[0]?.xUnit}
          yUnit={correlationData[0]?.yUnit}
        />
      )}

      {/* Data Table */}
      {correlationData.length > 0 && !isSameParameter && (
        <DataTable
          title="Correlation Data Table"
          data={correlationData}
          columns={tableColumns}
          searchable={true}
          searchPlaceholder="Filter by QID..."
          searchKey="qid"
          className="col-span-3"
          emptyMessage="Select parameters to view correlation data"
        />
      )}
    </div>
  );
}
