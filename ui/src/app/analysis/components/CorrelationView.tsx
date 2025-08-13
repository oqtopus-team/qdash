"use client";

import { useState, useEffect, useMemo, useCallback } from "react";

import Select from "react-select";

import { ChipSelector } from "@/app/components/ChipSelector";
import { DateSelector } from "@/app/components/DateSelector";
import { useDateNavigation } from "@/app/hooks/useDateNavigation";
import {
  useListChips,
  useFetchLatestQubitTaskGroupedByChip,
  useFetchHistoricalQubitTaskGroupedByChip,
} from "@/client/chip/chip";
import { PlotCard } from "@/shared/components/PlotCard";
import { useCSVExport } from "@/shared/hooks/useCSVExport";

// Task names and types mapping (same as CumulativeView)
const TASK_CONFIG: Record<
  string,
  { name: string; type: "qubit" | "coupling" }
> = {
  t1: { name: "CheckT1", type: "qubit" },
  t2_echo: { name: "CheckT2Echo", type: "qubit" },
  t2_star: { name: "CheckRamsey", type: "qubit" },
  gate_fidelity: { name: "RandomizedBenchmarking", type: "qubit" },
  x90_fidelity: { name: "X90InterleavedRandomizedBenchmarking", type: "qubit" },
  x180_fidelity: {
    name: "X180InterleavedRandomizedBenchmarking",
    type: "qubit",
  },
  zx90_fidelity: {
    name: "ZX90InterleavedRandomizedBenchmarking",
    type: "coupling",
  },
  readout_fidelity: { name: "ReadoutClassification", type: "qubit" },
};

// Parameter configuration
const PARAMETER_CONFIG: Record<
  string,
  {
    label: string;
    unit: string;
    displayUnit: string;
  }
> = {
  t1: { label: "T1 Coherence", unit: "µs", displayUnit: "µs" },
  t2_echo: { label: "T2 Echo", unit: "µs", displayUnit: "µs" },
  t2_star: { label: "T2 Star", unit: "µs", displayUnit: "µs" },
  gate_fidelity: {
    label: "Gate Fidelity (Clifford RB)",
    unit: "fidelity",
    displayUnit: "fidelity",
  },
  x90_fidelity: {
    label: "X90 Gate Fidelity",
    unit: "fidelity",
    displayUnit: "fidelity",
  },
  x180_fidelity: {
    label: "X180 Gate Fidelity",
    unit: "fidelity",
    displayUnit: "fidelity",
  },
  zx90_fidelity: {
    label: "ZX90 Gate Fidelity (2Q)",
    unit: "fidelity",
    displayUnit: "fidelity",
  },
  readout_fidelity: {
    label: "Readout Fidelity",
    unit: "fidelity",
    displayUnit: "fidelity",
  },
};

// Output parameter names for each task
const OUTPUT_PARAM_NAMES: Record<string, string> = {
  t1: "t1",
  t2_echo: "t2_echo",
  t2_star: "t2_star",
  gate_fidelity: "average_gate_fidelity",
  x90_fidelity: "x90_gate_fidelity",
  x180_fidelity: "x180_gate_fidelity",
  zx90_fidelity: "zx90_gate_fidelity",
  readout_fidelity: "average_readout_fidelity",
};

interface CorrelationDataPoint {
  qid: string;
  parameters: Record<string, number>;
}

interface CorrelationResult {
  parameterA: string;
  parameterB: string;
  correlation: number;
  pValue?: number;
  sampleSize: number;
}

// Pearson correlation coefficient calculation
function calculatePearsonCorrelation(
  x: number[],
  y: number[],
): { r: number; n: number } {
  if (x.length !== y.length || x.length === 0) {
    return { r: 0, n: 0 };
  }

  const n = x.length;
  const meanX = x.reduce((sum, val) => sum + val, 0) / n;
  const meanY = y.reduce((sum, val) => sum + val, 0) / n;

  let numerator = 0;
  let sumXSq = 0;
  let sumYSq = 0;

  for (let i = 0; i < n; i++) {
    const deltaX = x[i] - meanX;
    const deltaY = y[i] - meanY;
    numerator += deltaX * deltaY;
    sumXSq += deltaX * deltaX;
    sumYSq += deltaY * deltaY;
  }

  const denominator = Math.sqrt(sumXSq * sumYSq);
  const r = denominator === 0 ? 0 : numerator / denominator;

  return { r, n };
}

// Calculate correlation matrix for selected parameters
function calculateCorrelationMatrix(
  dataPoints: CorrelationDataPoint[],
  parameters: string[],
): CorrelationResult[] {
  const results: CorrelationResult[] = [];

  for (let i = 0; i < parameters.length; i++) {
    for (let j = i + 1; j < parameters.length; j++) {
      const paramA = parameters[i];
      const paramB = parameters[j];

      // Extract valid values for both parameters
      const validPoints = dataPoints.filter(
        (point) =>
          point.parameters[paramA] !== undefined &&
          point.parameters[paramB] !== undefined &&
          !isNaN(point.parameters[paramA]) &&
          !isNaN(point.parameters[paramB]),
      );

      if (validPoints.length >= 3) {
        // Minimum 3 points for meaningful correlation
        const xValues = validPoints.map((point) => point.parameters[paramA]);
        const yValues = validPoints.map((point) => point.parameters[paramB]);

        const { r, n } = calculatePearsonCorrelation(xValues, yValues);

        results.push({
          parameterA: paramA,
          parameterB: paramB,
          correlation: r,
          sampleSize: n,
        });
      }
    }
  }

  return results;
}

// Generate correlation heatmap data for Plotly
function generateHeatmapData(
  correlationResults: CorrelationResult[],
  parameters: string[],
): {
  z: number[][];
  x: string[];
  y: string[];
  text: string[][];
  hovertext: string[][];
} {
  const n = parameters.length;
  const correlationMatrix: number[][] = Array(n)
    .fill(null)
    .map(() => Array(n).fill(0));
  const textMatrix: string[][] = Array(n)
    .fill(null)
    .map(() => Array(n).fill(""));
  const hovertextMatrix: string[][] = Array(n)
    .fill(null)
    .map(() => Array(n).fill(""));

  // Fill diagonal with 1.0 (self-correlation)
  for (let i = 0; i < n; i++) {
    correlationMatrix[i][i] = 1.0;
    textMatrix[i][i] = "1.000";
    hovertextMatrix[i][i] =
      `${PARAMETER_CONFIG[parameters[i]].label}<br>Self-correlation: 1.000`;
  }

  // Fill correlation matrix with results
  correlationResults.forEach((result) => {
    const iA = parameters.indexOf(result.parameterA);
    const iB = parameters.indexOf(result.parameterB);

    if (iA !== -1 && iB !== -1) {
      // Fill both upper and lower triangle (symmetric matrix)
      correlationMatrix[iA][iB] = result.correlation;
      correlationMatrix[iB][iA] = result.correlation;

      const corrText = result.correlation.toFixed(3);
      const hoverText = `${PARAMETER_CONFIG[result.parameterA].label} vs<br>${PARAMETER_CONFIG[result.parameterB].label}<br>Correlation: ${corrText}<br>Sample size: ${result.sampleSize}`;

      textMatrix[iA][iB] = corrText;
      textMatrix[iB][iA] = corrText;
      hovertextMatrix[iA][iB] = hoverText;
      hovertextMatrix[iB][iA] = hoverText;
    }
  });

  const labels = parameters.map((param) => PARAMETER_CONFIG[param].label);

  return {
    z: correlationMatrix,
    x: labels,
    y: labels,
    text: textMatrix,
    hovertext: hovertextMatrix,
  };
}

export function CorrelationView() {
  // State management
  const [selectedChip, setSelectedChip] = useState<string>("");
  const [selectedDate, setSelectedDate] = useState<string>("latest");
  const [selectedParameters, setSelectedParameters] = useState<string[]>([
    "t1",
    "t2_echo",
    "t2_star",
    "gate_fidelity",
  ]);
  const [correlationThreshold, setCorrelationThreshold] = useState<number>(0.1);
  const [viewMode, setViewMode] = useState<"heatmap" | "scatter">("heatmap");
  const [scatterParameterX, setScatterParameterX] = useState<string>("t1");
  const [scatterParameterY, setScatterParameterY] =
    useState<string>("gate_fidelity");

  // Debug state
  console.log("CorrelationView State:", {
    selectedChip,
    selectedDate,
    selectedParameters,
    correlationThreshold,
  });

  // Available parameters for correlation analysis - all qubit parameters
  const availableParameters = Object.keys(TASK_CONFIG)
    .filter((key) => TASK_CONFIG[key].type === "qubit") // Only qubit parameters (not coupling)
    .map((key) => ({
      value: key,
      label: PARAMETER_CONFIG[key].label,
    }));

  // Fetch chips data for default selection
  const { data: chipsResponse } = useListChips();

  // Date navigation functionality
  const {
    navigateToPreviousDay,
    navigateToNextDay,
    canNavigatePrevious,
    canNavigateNext,
  } = useDateNavigation(selectedChip, selectedDate, setSelectedDate);

  // Set default chip on component mount
  useEffect(() => {
    if (!selectedChip && chipsResponse?.data && chipsResponse.data.length > 0) {
      // Sort chips by installation date and select the most recent one
      const sortedChips = [...chipsResponse.data].sort((a, b) => {
        const dateA = a.installed_at ? new Date(a.installed_at).getTime() : 0;
        const dateB = b.installed_at ? new Date(b.installed_at).getTime() : 0;
        return dateB - dateA;
      });
      setSelectedChip(sortedChips[0].chip_id);
    }
  }, [selectedChip, chipsResponse]);

  // Data fetching for all qubit parameters - fetch everything upfront
  // T1 parameter
  const t1LatestQuery = useFetchLatestQubitTaskGroupedByChip(
    selectedChip,
    TASK_CONFIG.t1?.name || "",
    {
      query: {
        enabled: Boolean(
          selectedChip && TASK_CONFIG.t1?.name && selectedDate === "latest",
        ),
        refetchInterval: selectedDate === "latest" ? 30000 : undefined,
        staleTime: 25000,
      },
    },
  );

  const t1HistoricalQuery = useFetchHistoricalQubitTaskGroupedByChip(
    selectedChip,
    TASK_CONFIG.t1?.name || "",
    selectedDate,
    {
      query: {
        enabled: Boolean(
          selectedChip && TASK_CONFIG.t1?.name && selectedDate !== "latest",
        ),
        staleTime: 60000,
      },
    },
  );

  // T2 Echo parameter
  const t2EchoLatestQuery = useFetchLatestQubitTaskGroupedByChip(
    selectedChip,
    TASK_CONFIG.t2_echo?.name || "",
    {
      query: {
        enabled: Boolean(
          selectedChip &&
            TASK_CONFIG.t2_echo?.name &&
            selectedDate === "latest",
        ),
        refetchInterval: selectedDate === "latest" ? 30000 : undefined,
        staleTime: 25000,
      },
    },
  );

  const t2EchoHistoricalQuery = useFetchHistoricalQubitTaskGroupedByChip(
    selectedChip,
    TASK_CONFIG.t2_echo?.name || "",
    selectedDate,
    {
      query: {
        enabled: Boolean(
          selectedChip &&
            TASK_CONFIG.t2_echo?.name &&
            selectedDate !== "latest",
        ),
        staleTime: 60000,
      },
    },
  );

  // T2 Star parameter
  const t2StarLatestQuery = useFetchLatestQubitTaskGroupedByChip(
    selectedChip,
    TASK_CONFIG.t2_star?.name || "",
    {
      query: {
        enabled: Boolean(
          selectedChip &&
            TASK_CONFIG.t2_star?.name &&
            selectedDate === "latest",
        ),
        refetchInterval: selectedDate === "latest" ? 30000 : undefined,
        staleTime: 25000,
      },
    },
  );

  const t2StarHistoricalQuery = useFetchHistoricalQubitTaskGroupedByChip(
    selectedChip,
    TASK_CONFIG.t2_star?.name || "",
    selectedDate,
    {
      query: {
        enabled: Boolean(
          selectedChip &&
            TASK_CONFIG.t2_star?.name &&
            selectedDate !== "latest",
        ),
        staleTime: 60000,
      },
    },
  );

  // Gate Fidelity parameter
  const gateFidelityLatestQuery = useFetchLatestQubitTaskGroupedByChip(
    selectedChip,
    TASK_CONFIG.gate_fidelity?.name || "",
    {
      query: {
        enabled: Boolean(
          selectedChip &&
            TASK_CONFIG.gate_fidelity?.name &&
            selectedDate === "latest",
        ),
        refetchInterval: selectedDate === "latest" ? 30000 : undefined,
        staleTime: 25000,
      },
    },
  );

  const gateFidelityHistoricalQuery = useFetchHistoricalQubitTaskGroupedByChip(
    selectedChip,
    TASK_CONFIG.gate_fidelity?.name || "",
    selectedDate,
    {
      query: {
        enabled: Boolean(
          selectedChip &&
            TASK_CONFIG.gate_fidelity?.name &&
            selectedDate !== "latest",
        ),
        staleTime: 60000,
      },
    },
  );

  // X90 Gate Fidelity parameter
  const x90FidelityLatestQuery = useFetchLatestQubitTaskGroupedByChip(
    selectedChip,
    TASK_CONFIG.x90_fidelity?.name || "",
    {
      query: {
        enabled: Boolean(
          selectedChip &&
            TASK_CONFIG.x90_fidelity?.name &&
            selectedDate === "latest",
        ),
        refetchInterval: selectedDate === "latest" ? 30000 : undefined,
        staleTime: 25000,
      },
    },
  );

  const x90FidelityHistoricalQuery = useFetchHistoricalQubitTaskGroupedByChip(
    selectedChip,
    TASK_CONFIG.x90_fidelity?.name || "",
    selectedDate,
    {
      query: {
        enabled: Boolean(
          selectedChip &&
            TASK_CONFIG.x90_fidelity?.name &&
            selectedDate !== "latest",
        ),
        staleTime: 60000,
      },
    },
  );

  // X180 Gate Fidelity parameter
  const x180FidelityLatestQuery = useFetchLatestQubitTaskGroupedByChip(
    selectedChip,
    TASK_CONFIG.x180_fidelity?.name || "",
    {
      query: {
        enabled: Boolean(
          selectedChip &&
            TASK_CONFIG.x180_fidelity?.name &&
            selectedDate === "latest",
        ),
        refetchInterval: selectedDate === "latest" ? 30000 : undefined,
        staleTime: 25000,
      },
    },
  );

  const x180FidelityHistoricalQuery = useFetchHistoricalQubitTaskGroupedByChip(
    selectedChip,
    TASK_CONFIG.x180_fidelity?.name || "",
    selectedDate,
    {
      query: {
        enabled: Boolean(
          selectedChip &&
            TASK_CONFIG.x180_fidelity?.name &&
            selectedDate !== "latest",
        ),
        staleTime: 60000,
      },
    },
  );

  // Readout Fidelity parameter
  const readoutFidelityLatestQuery = useFetchLatestQubitTaskGroupedByChip(
    selectedChip,
    TASK_CONFIG.readout_fidelity?.name || "",
    {
      query: {
        enabled: Boolean(
          selectedChip &&
            TASK_CONFIG.readout_fidelity?.name &&
            selectedDate === "latest",
        ),
        refetchInterval: selectedDate === "latest" ? 30000 : undefined,
        staleTime: 25000,
      },
    },
  );

  const readoutFidelityHistoricalQuery =
    useFetchHistoricalQubitTaskGroupedByChip(
      selectedChip,
      TASK_CONFIG.readout_fidelity?.name || "",
      selectedDate,
      {
        query: {
          enabled: Boolean(
            selectedChip &&
              TASK_CONFIG.readout_fidelity?.name &&
              selectedDate !== "latest",
          ),
          staleTime: 60000,
        },
      },
    );

  // Create parameter data queries object - include ALL parameters
  const parameterDataQueries = useMemo(() => {
    // Always fetch all available parameters regardless of selection
    const allParameterQueries = [
      {
        parameter: "t1",
        taskName: TASK_CONFIG.t1?.name,
        data:
          selectedDate === "latest"
            ? t1LatestQuery.data
            : t1HistoricalQuery.data,
        isLoading:
          selectedDate === "latest"
            ? t1LatestQuery.isLoading
            : t1HistoricalQuery.isLoading,
        error:
          selectedDate === "latest"
            ? t1LatestQuery.error
            : t1HistoricalQuery.error,
      },
      {
        parameter: "t2_echo",
        taskName: TASK_CONFIG.t2_echo?.name,
        data:
          selectedDate === "latest"
            ? t2EchoLatestQuery.data
            : t2EchoHistoricalQuery.data,
        isLoading:
          selectedDate === "latest"
            ? t2EchoLatestQuery.isLoading
            : t2EchoHistoricalQuery.isLoading,
        error:
          selectedDate === "latest"
            ? t2EchoLatestQuery.error
            : t2EchoHistoricalQuery.error,
      },
      {
        parameter: "t2_star",
        taskName: TASK_CONFIG.t2_star?.name,
        data:
          selectedDate === "latest"
            ? t2StarLatestQuery.data
            : t2StarHistoricalQuery.data,
        isLoading:
          selectedDate === "latest"
            ? t2StarLatestQuery.isLoading
            : t2StarHistoricalQuery.isLoading,
        error:
          selectedDate === "latest"
            ? t2StarLatestQuery.error
            : t2StarHistoricalQuery.error,
      },
      {
        parameter: "gate_fidelity",
        taskName: TASK_CONFIG.gate_fidelity?.name,
        data:
          selectedDate === "latest"
            ? gateFidelityLatestQuery.data
            : gateFidelityHistoricalQuery.data,
        isLoading:
          selectedDate === "latest"
            ? gateFidelityLatestQuery.isLoading
            : gateFidelityHistoricalQuery.isLoading,
        error:
          selectedDate === "latest"
            ? gateFidelityLatestQuery.error
            : gateFidelityHistoricalQuery.error,
      },
      {
        parameter: "x90_fidelity",
        taskName: TASK_CONFIG.x90_fidelity?.name,
        data:
          selectedDate === "latest"
            ? x90FidelityLatestQuery.data
            : x90FidelityHistoricalQuery.data,
        isLoading:
          selectedDate === "latest"
            ? x90FidelityLatestQuery.isLoading
            : x90FidelityHistoricalQuery.isLoading,
        error:
          selectedDate === "latest"
            ? x90FidelityLatestQuery.error
            : x90FidelityHistoricalQuery.error,
      },
      {
        parameter: "x180_fidelity",
        taskName: TASK_CONFIG.x180_fidelity?.name,
        data:
          selectedDate === "latest"
            ? x180FidelityLatestQuery.data
            : x180FidelityHistoricalQuery.data,
        isLoading:
          selectedDate === "latest"
            ? x180FidelityLatestQuery.isLoading
            : x180FidelityHistoricalQuery.isLoading,
        error:
          selectedDate === "latest"
            ? x180FidelityLatestQuery.error
            : x180FidelityHistoricalQuery.error,
      },
      {
        parameter: "readout_fidelity",
        taskName: TASK_CONFIG.readout_fidelity?.name,
        data:
          selectedDate === "latest"
            ? readoutFidelityLatestQuery.data
            : readoutFidelityHistoricalQuery.data,
        isLoading:
          selectedDate === "latest"
            ? readoutFidelityLatestQuery.isLoading
            : readoutFidelityHistoricalQuery.isLoading,
        error:
          selectedDate === "latest"
            ? readoutFidelityLatestQuery.error
            : readoutFidelityHistoricalQuery.error,
      },
    ];

    return allParameterQueries;
  }, [
    selectedDate,
    // T1 queries
    t1LatestQuery.data,
    t1LatestQuery.isLoading,
    t1LatestQuery.error,
    t1HistoricalQuery.data,
    t1HistoricalQuery.isLoading,
    t1HistoricalQuery.error,
    // T2 Echo queries
    t2EchoLatestQuery.data,
    t2EchoLatestQuery.isLoading,
    t2EchoLatestQuery.error,
    t2EchoHistoricalQuery.data,
    t2EchoHistoricalQuery.isLoading,
    t2EchoHistoricalQuery.error,
    // T2 Star queries
    t2StarLatestQuery.data,
    t2StarLatestQuery.isLoading,
    t2StarLatestQuery.error,
    t2StarHistoricalQuery.data,
    t2StarHistoricalQuery.isLoading,
    t2StarHistoricalQuery.error,
    // Gate Fidelity queries
    gateFidelityLatestQuery.data,
    gateFidelityLatestQuery.isLoading,
    gateFidelityLatestQuery.error,
    gateFidelityHistoricalQuery.data,
    gateFidelityHistoricalQuery.isLoading,
    gateFidelityHistoricalQuery.error,
    // X90 Fidelity queries
    x90FidelityLatestQuery.data,
    x90FidelityLatestQuery.isLoading,
    x90FidelityLatestQuery.error,
    x90FidelityHistoricalQuery.data,
    x90FidelityHistoricalQuery.isLoading,
    x90FidelityHistoricalQuery.error,
    // X180 Fidelity queries
    x180FidelityLatestQuery.data,
    x180FidelityLatestQuery.isLoading,
    x180FidelityLatestQuery.error,
    x180FidelityHistoricalQuery.data,
    x180FidelityHistoricalQuery.isLoading,
    x180FidelityHistoricalQuery.error,
    // Readout Fidelity queries
    readoutFidelityLatestQuery.data,
    readoutFidelityLatestQuery.isLoading,
    readoutFidelityLatestQuery.error,
    readoutFidelityHistoricalQuery.data,
    readoutFidelityHistoricalQuery.isLoading,
    readoutFidelityHistoricalQuery.error,
  ]);

  // Process correlation data
  const { correlationResults, isLoading, error } = useMemo(() => {
    // Debug logging
    console.log("CorrelationView Debug:", {
      selectedParameters,
      selectedChip,
      selectedDate,
      parameterDataQueriesLength: parameterDataQueries?.length,
      parameterDataQueries: parameterDataQueries?.map((q) => ({
        parameter: q.parameter,
        taskName: q.taskName,
        hasData: !!q.data?.data?.result,
        isLoading: q.isLoading,
        error: q.error?.message,
        dataKeys: q.data?.data?.result ? Object.keys(q.data.data.result) : [],
        sampleData: q.data?.data?.result
          ? Object.entries(q.data.data.result).slice(0, 1)
          : [],
      })),
    });

    // Check if any queries are loading
    const anyLoading =
      parameterDataQueries?.some((query) => query.isLoading) || false;
    const anyError = parameterDataQueries?.find((query) => query.error);

    if (anyLoading || selectedParameters.length < 2) {
      return {
        correlationResults: [],
        isLoading: anyLoading,
        error: anyError?.error,
      };
    }

    // Collect data points for all qubits across all parameters
    const dataPoints: CorrelationDataPoint[] = [];
    const qubitIds = new Set<string>();

    // First pass: collect all qubit IDs
    parameterDataQueries.forEach((query) => {
      if (query.data?.data?.result) {
        Object.keys(query.data.data.result).forEach((qid) => qubitIds.add(qid));
      }
    });

    // Second pass: build data points for each qubit
    Array.from(qubitIds).forEach((qid) => {
      const dataPoint: CorrelationDataPoint = {
        qid,
        parameters: {},
      };

      // Process ALL parameters for this qubit (we'll filter later)
      parameterDataQueries.forEach((query) => {
        if (query.data?.data?.result?.[qid]?.output_parameters) {
          const outputParamName = OUTPUT_PARAM_NAMES[query.parameter];
          const paramValue =
            query.data.data.result[qid].output_parameters[outputParamName];

          console.log(`Debug ${qid} ${query.parameter}:`, {
            outputParamName,
            rawValue: paramValue,
            valueType: typeof paramValue,
            rawValueKeys:
              typeof paramValue === "object" && paramValue !== null
                ? Object.keys(paramValue)
                : null,
            rawValueContent:
              typeof paramValue === "object" && paramValue !== null
                ? paramValue
                : null,
          });

          if (paramValue !== null && paramValue !== undefined) {
            let value: number;

            // Handle different data structures
            if (typeof paramValue === "number") {
              value = paramValue;
            } else if (typeof paramValue === "string") {
              value = Number(paramValue);
            } else if (typeof paramValue === "object" && paramValue !== null) {
              // Handle nested object with value property (e.g., {value: 123, error: 0.1})
              if (
                "value" in paramValue &&
                typeof paramValue.value === "number"
              ) {
                value = paramValue.value;
              } else if (
                "mean" in paramValue &&
                typeof paramValue.mean === "number"
              ) {
                value = paramValue.mean;
              } else if (
                "result" in paramValue &&
                typeof paramValue.result === "number"
              ) {
                value = paramValue.result;
              } else {
                console.warn(
                  `Unknown object structure for ${query.parameter}:`,
                  paramValue,
                );
                return;
              }
            } else {
              console.warn(
                `Cannot process value type for ${query.parameter}:`,
                typeof paramValue,
              );
              return;
            }

            const originalValue = value;

            // No unit conversion needed - data is already in correct units

            console.log(`Unit conversion for ${query.parameter}:`, {
              original: originalValue,
              converted: value,
              isValid: !isNaN(value) && value > 0,
            });

            if (!isNaN(value) && value > 0) {
              dataPoint.parameters[query.parameter] = value;
            }
          }
        }
      });

      // Add data points that have at least 2 of any parameters
      // We'll filter by selectedParameters when calculating correlations
      if (Object.keys(dataPoint.parameters).length >= 2) {
        dataPoints.push(dataPoint);
      }
    });

    // Calculate correlation matrix ONLY for selected parameters
    const correlationResults = calculateCorrelationMatrix(
      dataPoints,
      selectedParameters,
    );

    console.log("CorrelationView Data Processing:", {
      qubitIds: Array.from(qubitIds),
      dataPoints: dataPoints.map((dp) => ({
        qid: dp.qid,
        parameters: Object.keys(dp.parameters),
      })),
      correlationResults: correlationResults.length,
    });

    return {
      correlationResults,
      isLoading: false,
      error: anyError?.error,
    };
  }, [parameterDataQueries, selectedParameters]);

  // Generate heatmap plot data
  const heatmapPlotData = useMemo(() => {
    if (
      selectedParameters.length < 2 ||
      isLoading ||
      correlationResults.length === 0
    ) {
      return [];
    }

    const heatmapData = generateHeatmapData(
      correlationResults,
      selectedParameters,
    );

    return [
      {
        z: heatmapData.z,
        x: heatmapData.x,
        y: heatmapData.y,
        text: heatmapData.text as any, // 2D array for heatmap text display
        hovertext: heatmapData.hovertext as any, // 2D array for heatmap hover
        type: "heatmap" as const,
        colorscale: [
          [0, "#d73027"], // Strong negative correlation
          [0.25, "#f46d43"], // Moderate negative
          [0.4, "#fdae61"], // Weak negative
          [0.5, "#ffffff"], // No correlation
          [0.6, "#abd9e9"], // Weak positive
          [0.75, "#74add1"], // Moderate positive
          [1, "#4575b4"], // Strong positive correlation
        ],
        zmid: 0,
        zmin: -1,
        zmax: 1,
        hovertemplate: "%{hovertext}<extra></extra>",
        texttemplate: "%{text}",
        textfont: {
          size: 12,
          color: "black",
        },
        showscale: true,
        colorbar: {
          title: {
            text: "Correlation<br>Coefficient",
            side: "right",
          },
          titleside: "right",
          thickness: 15,
          len: 0.7,
          tickmode: "array",
          tickvals: [-1, -0.5, 0, 0.5, 1],
          ticktext: ["-1.0", "-0.5", "0.0", "+0.5", "+1.0"],
        },
      } as any,
    ];
  }, [correlationResults, selectedParameters, isLoading]);

  // Helper function to extract numeric value from different data structures
  const extractNumericValue = useCallback((paramValue: any): number | null => {
    if (typeof paramValue === "number") {
      return paramValue;
    } else if (typeof paramValue === "string") {
      return Number(paramValue);
    } else if (typeof paramValue === "object" && paramValue !== null) {
      if ("value" in paramValue && typeof paramValue.value === "number") {
        return paramValue.value;
      } else if ("mean" in paramValue && typeof paramValue.mean === "number") {
        return paramValue.mean;
      } else if (
        "result" in paramValue &&
        typeof paramValue.result === "number"
      ) {
        return paramValue.result;
      }
    }
    return null;
  }, []);

  // Generate scatter plot data for selected parameter pair
  const scatterPlotData = useMemo(() => {
    if (
      viewMode !== "scatter" ||
      !scatterParameterX ||
      !scatterParameterY ||
      scatterParameterX === scatterParameterY
    ) {
      return [];
    }

    // Find the queries for the selected parameters (now always available)
    const paramXQuery = parameterDataQueries?.find(
      (q) => q.parameter === scatterParameterX,
    );
    const paramYQuery = parameterDataQueries?.find(
      (q) => q.parameter === scatterParameterY,
    );

    if (!paramXQuery?.data?.data?.result || !paramYQuery?.data?.data?.result) {
      return [];
    }

    const scatterPoints: Array<{
      x: number;
      y: number;
      text: string;
      qid: string;
    }> = [];
    const qubitIds = new Set([
      ...Object.keys(paramXQuery.data.data.result),
      ...Object.keys(paramYQuery.data.data.result),
    ]);

    qubitIds.forEach((qid) => {
      const taskXResult = paramXQuery.data?.data?.result?.[qid];
      const taskYResult = paramYQuery.data?.data?.result?.[qid];

      if (taskXResult?.output_parameters && taskYResult?.output_parameters) {
        const xOutputParam = OUTPUT_PARAM_NAMES[scatterParameterX];
        const yOutputParam = OUTPUT_PARAM_NAMES[scatterParameterY];

        const xParamValue = taskXResult.output_parameters[xOutputParam];
        const yParamValue = taskYResult.output_parameters[yOutputParam];

        if (xParamValue != null && yParamValue != null) {
          let xValue = extractNumericValue(xParamValue);
          let yValue = extractNumericValue(yParamValue);

          if (xValue !== null && yValue !== null) {
            // No unit conversion needed - data is already in correct units

            if (!isNaN(xValue) && xValue > 0 && !isNaN(yValue) && yValue > 0) {
              scatterPoints.push({
                x: xValue,
                y: yValue,
                text: `Qubit ${qid}`,
                qid: qid,
              });
            }
          }
        }
      }
    });

    // Calculate correlation for this pair
    const xValues = scatterPoints.map((p) => p.x);
    const yValues = scatterPoints.map((p) => p.y);
    const correlation = calculatePearsonCorrelation(xValues, yValues);

    return [
      {
        x: scatterPoints.map((p) => p.x),
        y: scatterPoints.map((p) => p.y),
        text: scatterPoints.map((p) => p.text),
        type: "scatter" as const,
        mode: "markers" as const,
        marker: {
          size: 8,
          color: scatterPoints.map((p) => parseInt(p.qid)),
          colorscale: "Viridis",
          colorbar: {
            title: "Qubit ID",
            thickness: 15,
            len: 0.7,
          },
          opacity: 0.7,
          line: {
            width: 1,
            color: "white",
          },
        },
        name: `${PARAMETER_CONFIG[scatterParameterX].label} vs ${PARAMETER_CONFIG[scatterParameterY].label}`,
        hovertemplate:
          `%{text}<br>` +
          `${PARAMETER_CONFIG[scatterParameterX].label}: %{x}<br>` +
          `${PARAMETER_CONFIG[scatterParameterY].label}: %{y}<br>` +
          `<extra></extra>`,
        correlation: correlation.r,
        sampleSize: correlation.n,
      },
    ];
  }, [
    viewMode,
    scatterParameterX,
    scatterParameterY,
    parameterDataQueries,
    extractNumericValue,
  ]);

  // CSV Export
  const { exportToCSV } = useCSVExport();

  const handleExportCSV = () => {
    if (correlationResults.length === 0) return;

    const headers = [
      "Parameter_A",
      "Parameter_B",
      "Correlation",
      "Sample_Size",
      "Abs_Correlation",
      "Chip",
      "Date",
    ];
    const rows = correlationResults.map((result) => [
      PARAMETER_CONFIG[result.parameterA].label,
      PARAMETER_CONFIG[result.parameterB].label,
      result.correlation.toFixed(6),
      result.sampleSize.toString(),
      Math.abs(result.correlation).toFixed(6),
      selectedChip,
      selectedDate === "latest" ? "latest" : selectedDate,
    ]);

    const timestamp = new Date()
      .toISOString()
      .slice(0, 19)
      .replace(/[:-]/g, "");
    const dateStr = selectedDate === "latest" ? "latest" : selectedDate;
    const filename = `correlation_${selectedChip}_${dateStr}_${timestamp}.csv`;

    exportToCSV({ filename, headers, data: rows });
  };

  return (
    <div className="space-y-6">
      {/* Controls Section */}
      <div className="card bg-base-100 shadow-md">
        <div className="card-body">
          {/* View Mode Selection */}
          <div className="flex justify-between items-center mb-4">
            <h2 className="text-lg font-semibold">
              Parameter Correlation Analysis
            </h2>
            <div className="join">
              <button
                className={`join-item btn btn-sm ${viewMode === "heatmap" ? "btn-active" : ""}`}
                onClick={() => setViewMode("heatmap")}
              >
                Heatmap
              </button>
              <button
                className={`join-item btn btn-sm ${viewMode === "scatter" ? "btn-active" : ""}`}
                onClick={() => setViewMode("scatter")}
              >
                Scatter Plot
              </button>
            </div>
          </div>

          <div className="flex flex-wrap items-end gap-4">
            {/* Chip Selection */}
            <div className="form-control min-w-48">
              <div className="h-8"></div>{" "}
              {/* Spacer to align with other form controls */}
              <div className="h-10">
                <ChipSelector
                  selectedChip={selectedChip}
                  onChipSelect={setSelectedChip}
                />
              </div>
            </div>

            {/* Date Selection */}
            <div className="form-control min-w-48">
              <div className="flex justify-center gap-1 h-8 items-center">
                <button
                  onClick={navigateToPreviousDay}
                  disabled={!canNavigatePrevious}
                  className="btn btn-xs btn-ghost"
                  title="Previous Day"
                >
                  ←
                </button>
                <button
                  onClick={navigateToNextDay}
                  disabled={!canNavigateNext}
                  className="btn btn-xs btn-ghost"
                  title="Next Day"
                >
                  →
                </button>
              </div>
              <div className="h-10">
                <DateSelector
                  chipId={selectedChip}
                  selectedDate={selectedDate}
                  onDateSelect={setSelectedDate}
                  disabled={!selectedChip}
                />
              </div>
            </div>

            {/* Parameter Selection - Dynamic based on view mode */}
            {viewMode === "heatmap" ? (
              <div className="form-control min-w-80">
                <div className="flex justify-between items-center h-8">
                  <span className="label-text font-semibold">Parameters</span>
                  <span className="text-xs text-gray-500">
                    Select 2+ parameters for correlation matrix
                  </span>
                </div>
                <div className="h-10">
                  <Select<{ value: string; label: string }, true>
                    isMulti
                    options={availableParameters}
                    value={availableParameters.filter((option) =>
                      selectedParameters.includes(option.value),
                    )}
                    onChange={(options) => {
                      const values = options
                        ? options.map((option) => option.value)
                        : [];
                      setSelectedParameters(values);
                    }}
                    placeholder="Select parameters to analyze"
                    className="text-base-content"
                    styles={{
                      control: (base) => ({
                        ...base,
                        minHeight: "40px",
                        height: "40px",
                        borderRadius: "0.5rem",
                      }),
                      valueContainer: (base) => ({
                        ...base,
                        height: "40px",
                        padding: "0 8px",
                      }),
                      input: (base) => ({
                        ...base,
                        margin: "0px",
                        padding: "0px",
                      }),
                      indicatorsContainer: (base) => ({
                        ...base,
                        height: "40px",
                      }),
                    }}
                  />
                </div>
              </div>
            ) : (
              <>
                {/* X-axis Parameter Selection */}
                <div className="form-control min-w-48">
                  <div className="flex justify-between items-center h-8">
                    <span className="label-text font-semibold">
                      X-axis Parameter
                    </span>
                  </div>
                  <div className="h-10">
                    <Select<{ value: string; label: string }>
                      options={availableParameters}
                      value={availableParameters.find(
                        (option) => option.value === scatterParameterX,
                      )}
                      onChange={(option) => {
                        if (option) {
                          setScatterParameterX(option.value);
                        }
                      }}
                      placeholder="Select X parameter"
                      className="text-base-content"
                      styles={{
                        control: (base) => ({
                          ...base,
                          minHeight: "40px",
                          height: "40px",
                          borderRadius: "0.5rem",
                        }),
                        valueContainer: (base) => ({
                          ...base,
                          height: "40px",
                          padding: "0 8px",
                        }),
                        input: (base) => ({
                          ...base,
                          margin: "0px",
                          padding: "0px",
                        }),
                        indicatorsContainer: (base) => ({
                          ...base,
                          height: "40px",
                        }),
                      }}
                    />
                  </div>
                </div>

                {/* Y-axis Parameter Selection */}
                <div className="form-control min-w-48">
                  <div className="flex justify-between items-center h-8">
                    <span className="label-text font-semibold">
                      Y-axis Parameter
                    </span>
                  </div>
                  <div className="h-10">
                    <Select<{ value: string; label: string }>
                      options={availableParameters}
                      value={availableParameters.find(
                        (option) => option.value === scatterParameterY,
                      )}
                      onChange={(option) => {
                        if (option) {
                          setScatterParameterY(option.value);
                        }
                      }}
                      placeholder="Select Y parameter"
                      className="text-base-content"
                      styles={{
                        control: (base) => ({
                          ...base,
                          minHeight: "40px",
                          height: "40px",
                          borderRadius: "0.5rem",
                        }),
                        valueContainer: (base) => ({
                          ...base,
                          height: "40px",
                          padding: "0 8px",
                        }),
                        input: (base) => ({
                          ...base,
                          margin: "0px",
                          padding: "0px",
                        }),
                        indicatorsContainer: (base) => ({
                          ...base,
                          height: "40px",
                        }),
                      }}
                    />
                  </div>
                </div>
              </>
            )}

            {/* Correlation Threshold - Only for heatmap mode */}
            {viewMode === "heatmap" && (
              <div className="form-control min-w-32">
                <label className="label h-8">
                  <span className="label-text font-semibold">Threshold</span>
                </label>
                <div className="h-10">
                  <input
                    type="range"
                    min="0"
                    max="1"
                    step="0.05"
                    value={correlationThreshold}
                    onChange={(e) =>
                      setCorrelationThreshold(Number(e.target.value))
                    }
                    className="range range-primary range-sm"
                  />
                  <div className="text-xs text-center mt-1">
                    {correlationThreshold.toFixed(2)}
                  </div>
                </div>
              </div>
            )}

            {/* Export Button */}
            <div className="form-control min-w-32">
              <label className="label h-8">
                <span className="label-text font-semibold">Export</span>
              </label>
              <div className="h-10">
                <button
                  className="btn btn-outline btn-sm h-full w-full"
                  onClick={handleExportCSV}
                  disabled={
                    viewMode === "heatmap"
                      ? selectedParameters.length < 2 ||
                        correlationResults.length === 0
                      : scatterPlotData.length === 0
                  }
                >
                  Export CSV
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="alert alert-error">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            className="stroke-current shrink-0 h-6 w-6"
            fill="none"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
          <span>
            Failed to load correlation data:{" "}
            {error.message || "An unexpected error occurred"}
          </span>
        </div>
      )}

      {/* Visualization Section */}
      {viewMode === "heatmap" ? (
        // Correlation Heatmap
        selectedParameters.length >= 2 &&
        !isLoading &&
        correlationResults.length > 0 ? (
          <PlotCard
            plotData={heatmapPlotData}
            layout={{
              title: {
                text: "Parameter Correlation Heatmap",
                font: { size: 18 },
              },
              xaxis: {
                title: "",
                side: "bottom",
                tickangle: -45,
                showgrid: false,
                zeroline: false,
                showline: false,
                ticks: "",
                showticklabels: true,
              },
              yaxis: {
                title: "",
                showgrid: false,
                zeroline: false,
                showline: false,
                ticks: "",
                showticklabels: true,
                autorange: "reversed" as const,
              },
              plot_bgcolor: "#ffffff",
              paper_bgcolor: "#ffffff",
              margin: { t: 60, r: 100, b: 120, l: 120 },
              annotations: [
                {
                  text: `Correlation matrix for ${selectedParameters.length} parameters<br>Sample: ${selectedChip}, Date: ${selectedDate === "latest" ? "Latest" : selectedDate}`,
                  showarrow: false,
                  xref: "paper" as const,
                  yref: "paper" as const,
                  x: 0.5,
                  y: -0.25,
                  xanchor: "center" as const,
                  yanchor: "top" as const,
                  font: { size: 11, color: "#666" },
                },
              ],
            }}
            isLoading={isLoading}
            title="Parameter Correlation Heatmap"
          />
        ) : (
          <div className="card bg-base-100 shadow-md">
            <div className="card-body">
              <div className="min-h-96">
                {selectedParameters.length < 2 ? (
                  <div className="flex items-center justify-center h-96 bg-base-200 rounded-lg">
                    <div className="text-center">
                      <div className="text-lg font-semibold mb-2">
                        Parameter Correlation Analysis
                      </div>
                      <div className="text-base-content/60">
                        Select at least 2 parameters to see correlation matrix
                      </div>
                    </div>
                  </div>
                ) : isLoading ? (
                  <div className="flex items-center justify-center h-96 bg-base-200 rounded-lg">
                    <div className="text-center">
                      <div className="text-lg font-semibold mb-2">
                        Loading Correlation Data
                      </div>
                      <div className="text-base-content/60 mb-4">
                        Analyzing correlations between:{" "}
                        {selectedParameters
                          .map((p) => PARAMETER_CONFIG[p].label)
                          .join(", ")}
                      </div>
                      <div className="loading loading-spinner loading-lg"></div>
                    </div>
                  </div>
                ) : (
                  <div className="flex items-center justify-center h-96 bg-base-200 rounded-lg">
                    <div className="text-center">
                      <div className="text-lg font-semibold mb-2">
                        No Correlation Data
                      </div>
                      <div className="text-base-content/60">
                        Insufficient data for correlation analysis.
                        <br />
                        Try selecting different parameters or date.
                      </div>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </div>
        )
      ) : // Scatter Plot
      scatterPlotData.length > 0 && scatterParameterX !== scatterParameterY ? (
        <PlotCard
          plotData={scatterPlotData}
          layout={{
            title: {
              text: `${PARAMETER_CONFIG[scatterParameterX].label} vs ${PARAMETER_CONFIG[scatterParameterY].label}`,
              font: { size: 18 },
            },
            xaxis: {
              title: `${PARAMETER_CONFIG[scatterParameterX].label}${PARAMETER_CONFIG[scatterParameterX].displayUnit !== "fidelity" ? ` (${PARAMETER_CONFIG[scatterParameterX].displayUnit})` : ""}`,
              showgrid: true,
              gridcolor: "#e5e7eb",
              zeroline: false,
            },
            yaxis: {
              title: `${PARAMETER_CONFIG[scatterParameterY].label}${PARAMETER_CONFIG[scatterParameterY].displayUnit !== "fidelity" ? ` (${PARAMETER_CONFIG[scatterParameterY].displayUnit})` : ""}`,
              showgrid: true,
              gridcolor: "#e5e7eb",
              zeroline: false,
            },
            plot_bgcolor: "#ffffff",
            paper_bgcolor: "#ffffff",
            margin: { t: 60, r: 100, b: 80, l: 100 },
            annotations: [
              {
                text: `Correlation: r = ${scatterPlotData[0]?.correlation?.toFixed(3) || "N/A"} (n = ${scatterPlotData[0]?.sampleSize || 0})<br>Sample: ${selectedChip}, Date: ${selectedDate === "latest" ? "Latest" : selectedDate}`,
                showarrow: false,
                xref: "paper" as const,
                yref: "paper" as const,
                x: 0.02,
                y: 0.98,
                xanchor: "left" as const,
                yanchor: "top" as const,
                font: { size: 11, color: "#666" },
                bgcolor: "rgba(255, 255, 255, 0.8)",
                bordercolor: "#e5e7eb",
                borderwidth: 1,
              },
            ],
          }}
          isLoading={isLoading}
          title={`${PARAMETER_CONFIG[scatterParameterX].label} vs ${PARAMETER_CONFIG[scatterParameterY].label} Scatter Plot`}
        />
      ) : (
        <div className="card bg-base-100 shadow-md">
          <div className="card-body">
            <div className="min-h-96">
              {scatterParameterX === scatterParameterY ? (
                <div className="flex items-center justify-center h-96 bg-base-200 rounded-lg">
                  <div className="text-center">
                    <div className="text-lg font-semibold mb-2">
                      Parameter Scatter Plot
                    </div>
                    <div className="text-base-content/60">
                      Please select different parameters for X and Y axes
                    </div>
                  </div>
                </div>
              ) : isLoading ? (
                <div className="flex items-center justify-center h-96 bg-base-200 rounded-lg">
                  <div className="text-center">
                    <div className="text-lg font-semibold mb-2">
                      Loading Scatter Plot Data
                    </div>
                    <div className="text-base-content/60 mb-4">
                      Analyzing: {PARAMETER_CONFIG[scatterParameterX].label} vs{" "}
                      {PARAMETER_CONFIG[scatterParameterY].label}
                    </div>
                    <div className="loading loading-spinner loading-lg"></div>
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-center h-96 bg-base-200 rounded-lg">
                  <div className="text-center">
                    <div className="text-lg font-semibold mb-2">
                      No Scatter Plot Data
                    </div>
                    <div className="text-base-content/60">
                      Insufficient data for scatter plot analysis.
                      <br />
                      Try selecting different parameters or date.
                    </div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {/* Correlation Results Table - Only show for heatmap mode */}
      {viewMode === "heatmap" &&
        selectedParameters.length >= 2 &&
        !isLoading &&
        correlationResults.length > 0 && (
          <div className="card bg-base-100 shadow-md">
            <div className="card-body">
              <div className="space-y-4">
                <h3 className="text-lg font-semibold">Correlation Details</h3>

                <div className="overflow-x-auto">
                  <table className="table table-zebra w-full">
                    <thead>
                      <tr>
                        <th>Parameter A</th>
                        <th>Parameter B</th>
                        <th>Correlation (r)</th>
                        <th>Strength</th>
                        <th>Sample Size</th>
                      </tr>
                    </thead>
                    <tbody>
                      {correlationResults
                        .filter(
                          (result) =>
                            Math.abs(result.correlation) >=
                            correlationThreshold,
                        )
                        .sort(
                          (a, b) =>
                            Math.abs(b.correlation) - Math.abs(a.correlation),
                        )
                        .map((result, index) => {
                          const absCorr = Math.abs(result.correlation);
                          const strength =
                            absCorr >= 0.7
                              ? "Strong"
                              : absCorr >= 0.3
                                ? "Moderate"
                                : "Weak";
                          const strengthColor =
                            absCorr >= 0.7
                              ? "text-success"
                              : absCorr >= 0.3
                                ? "text-warning"
                                : "text-info";

                          return (
                            <tr key={index}>
                              <td className="font-medium">
                                {PARAMETER_CONFIG[result.parameterA].label}
                              </td>
                              <td className="font-medium">
                                {PARAMETER_CONFIG[result.parameterB].label}
                              </td>
                              <td className="font-mono">
                                <span
                                  className={
                                    result.correlation >= 0
                                      ? "text-success"
                                      : "text-error"
                                  }
                                >
                                  {result.correlation.toFixed(3)}
                                </span>
                              </td>
                              <td className={strengthColor}>{strength}</td>
                              <td>{result.sampleSize}</td>
                            </tr>
                          );
                        })}
                    </tbody>
                  </table>
                </div>

                {correlationResults.filter(
                  (result) =>
                    Math.abs(result.correlation) >= correlationThreshold,
                ).length === 0 && (
                  <div className="text-center py-8 text-base-content/60">
                    No correlations above threshold (
                    {correlationThreshold.toFixed(2)})
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

      {/* Statistics Section */}
      {((viewMode === "heatmap" &&
        selectedParameters.length >= 2 &&
        correlationResults.length > 0) ||
        (viewMode === "scatter" && scatterPlotData.length > 0)) && (
        <div className="card bg-base-100 shadow-md">
          <div className="card-body">
            <h3 className="text-lg font-semibold mb-4">
              Correlation Statistics
            </h3>
            {viewMode === "heatmap" ? (
              <div className="stats shadow grid-cols-2 lg:grid-cols-5">
                <div className="stat">
                  <div className="stat-title">Parameters</div>
                  <div className="stat-value text-sm">
                    {selectedParameters.length}
                  </div>
                  <div className="stat-desc">Selected for analysis</div>
                </div>
                <div className="stat">
                  <div className="stat-title">Valid Pairs</div>
                  <div className="stat-value text-sm">
                    {correlationResults.length}
                  </div>
                  <div className="stat-desc">With sufficient data</div>
                </div>
                <div className="stat">
                  <div className="stat-title">Above Threshold</div>
                  <div className="stat-value text-sm">
                    {
                      correlationResults.filter(
                        (result) =>
                          Math.abs(result.correlation) >= correlationThreshold,
                      ).length
                    }
                  </div>
                  <div className="stat-desc">
                    ≥ {correlationThreshold.toFixed(2)} correlation
                  </div>
                </div>
                <div className="stat">
                  <div className="stat-title">Strongest</div>
                  <div className="stat-value text-sm">
                    {correlationResults.length > 0
                      ? Math.max(
                          ...correlationResults.map((r) =>
                            Math.abs(r.correlation),
                          ),
                        ).toFixed(3)
                      : "N/A"}
                  </div>
                  <div className="stat-desc">Absolute correlation</div>
                </div>
                <div className="stat">
                  <div className="stat-title">Avg Sample Size</div>
                  <div className="stat-value text-sm">
                    {correlationResults.length > 0
                      ? Math.round(
                          correlationResults.reduce(
                            (sum, r) => sum + r.sampleSize,
                            0,
                          ) / correlationResults.length,
                        )
                      : "N/A"}
                  </div>
                  <div className="stat-desc">Data points per pair</div>
                </div>
              </div>
            ) : (
              <div className="stats shadow grid-cols-2 lg:grid-cols-4">
                <div className="stat">
                  <div className="stat-title">X Parameter</div>
                  <div className="stat-value text-sm">
                    {PARAMETER_CONFIG[scatterParameterX].label}
                  </div>
                  <div className="stat-desc">Horizontal axis</div>
                </div>
                <div className="stat">
                  <div className="stat-title">Y Parameter</div>
                  <div className="stat-value text-sm">
                    {PARAMETER_CONFIG[scatterParameterY].label}
                  </div>
                  <div className="stat-desc">Vertical axis</div>
                </div>
                <div className="stat">
                  <div className="stat-title">Correlation</div>
                  <div className="stat-value text-sm">
                    {scatterPlotData[0]?.correlation?.toFixed(3) || "N/A"}
                  </div>
                  <div className="stat-desc">Pearson coefficient</div>
                </div>
                <div className="stat">
                  <div className="stat-title">Sample Size</div>
                  <div className="stat-value text-sm">
                    {scatterPlotData[0]?.sampleSize || 0}
                  </div>
                  <div className="stat-desc">Data points</div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
