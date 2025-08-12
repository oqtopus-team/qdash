"use client";

import { useState, useMemo, useEffect } from "react";
import {
  useListChips,
  useFetchLatestQubitTaskGroupedByChip,
  useFetchHistoricalQubitTaskGroupedByChip,
} from "@/client/chip/chip";
import { PlotCard } from "@/shared/components/PlotCard";
import { ErrorCard } from "@/shared/components/ErrorCard";
import { DataTable } from "@/shared/components/DataTable";
import { useCSVExport } from "@/shared/hooks/useCSVExport";
import { ChipSelector } from "@/app/components/ChipSelector";
import { DateSelector } from "@/app/components/DateSelector";
import { useDateNavigation } from "@/app/hooks/useDateNavigation";
import Select from "react-select";

// Task names and types mapping
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

// Parameter configuration: labels and directionality
const PARAMETER_CONFIG: Record<
  string,
  {
    label: string;
    higherIsBetter: boolean;
    unit: string;
    displayUnit: string;
  }
> = {
  t1: {
    label: "T1",
    higherIsBetter: true,
    unit: "µs",
    displayUnit: "µs",
  },
  t2_echo: {
    label: "T2 Echo",
    higherIsBetter: true,
    unit: "µs",
    displayUnit: "µs",
  },
  t2_star: {
    label: "T2*",
    higherIsBetter: true,
    unit: "µs",
    displayUnit: "µs",
  },
  gate_fidelity: {
    label: "Average Gate Fidelity",
    higherIsBetter: true, // Display as fidelity (higher is better)
    unit: "percentage",
    displayUnit: "%",
  },
  x90_fidelity: {
    label: "X90 Gate Fidelity",
    higherIsBetter: true, // Display as fidelity
    unit: "percentage",
    displayUnit: "%",
  },
  x180_fidelity: {
    label: "X180 Gate Fidelity",
    higherIsBetter: true, // Display as fidelity
    unit: "percentage",
    displayUnit: "%",
  },
  zx90_fidelity: {
    label: "ZX90 Gate Error (2Q)",
    higherIsBetter: false, // Changed: display as error
    unit: "error",
    displayUnit: "",
  },
  readout_fidelity: {
    label: "Readout Fidelity",
    higherIsBetter: true, // Display as fidelity
    unit: "percentage",
    displayUnit: "%",
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

interface CumulativeDataPoint {
  value: number;
  error?: number; // Uncertainty/error bar
  cdf: number;
  survivalFunction: number; // 1 - CDF for "bigger is better" metrics
  qid: string;
  r2?: number; // R-squared for fit quality (RB tasks)
}

export function CumulativeView() {
  // State management
  const [selectedChip, setSelectedChip] = useState<string>("");
  const [selectedParameters, setSelectedParameters] = useState<string[]>([
    "t1",
    "t2_echo",
    "t2_star",
  ]);
  const [selectedDate, setSelectedDate] = useState<string>("latest");
  const [showAsErrorRate, setShowAsErrorRate] = useState<boolean>(false);

  // Group parameters by category for better organization
  const parameterGroups = {
    coherence: ["t1", "t2_echo", "t2_star"],
    fidelity: ["gate_fidelity", "x90_fidelity", "x180_fidelity", "readout_fidelity"]
  };

  // Determine current parameter type to enforce mutual exclusivity
  const currentParameterType = useMemo(() => {
    if (selectedParameters.length === 0) return null;
    
    const hasCoherence = selectedParameters.some(p => parameterGroups.coherence.includes(p));
    const hasFidelity = selectedParameters.some(p => parameterGroups.fidelity.includes(p));
    
    return hasCoherence ? "coherence" : hasFidelity ? "fidelity" : null;
  }, [selectedParameters, parameterGroups]);

  // Available parameters based on current selection (mutually exclusive)
  const availableParameters = useMemo(() => {
    if (currentParameterType === "coherence") {
      return parameterGroups.coherence.map((key) => ({
        value: key,
        label: PARAMETER_CONFIG[key].label,
      }));
    } else if (currentParameterType === "fidelity") {
      return parameterGroups.fidelity.map((key) => ({
        value: key,
        label: PARAMETER_CONFIG[key].label,
      }));
    } else {
      // No selection yet - show both groups
      return [
        {
          label: "Coherence Times",
          options: parameterGroups.coherence.map((key) => ({
            value: key,
            label: PARAMETER_CONFIG[key].label,
          }))
        },
        {
          label: "Gate Fidelities", 
          options: parameterGroups.fidelity.map((key) => ({
            value: key,
            label: PARAMETER_CONFIG[key].label,
          }))
        }
      ];
    }
  }, [currentParameterType, parameterGroups]);

  // Fetch chips data for default selection
  const { data: chipsResponse } = useListChips();

  // Date navigation functionality
  const {
    navigateToPreviousDay,
    navigateToNextDay,
    canNavigatePrevious,
    canNavigateNext,
    formatDate,
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

  // Fetch data for T1
  const {
    data: t1LatestResponse,
    isLoading: t1LatestLoading,
    error: t1LatestError,
  } = useFetchLatestQubitTaskGroupedByChip(selectedChip, "CheckT1", {
    query: {
      enabled: Boolean(
        selectedChip &&
          selectedDate === "latest" &&
          selectedParameters.includes("t1"),
      ),
      refetchInterval: selectedDate === "latest" ? 30000 : undefined,
      staleTime: 25000,
    },
  });

  const {
    data: t1HistoricalResponse,
    isLoading: t1HistoricalLoading,
    error: t1HistoricalError,
  } = useFetchHistoricalQubitTaskGroupedByChip(
    selectedChip,
    "CheckT1",
    selectedDate,
    {
      query: {
        enabled: Boolean(
          selectedChip &&
            selectedDate !== "latest" &&
            selectedParameters.includes("t1"),
        ),
        staleTime: 60000,
      },
    },
  );

  // Fetch data for T2 Echo
  const {
    data: t2EchoLatestResponse,
    isLoading: t2EchoLatestLoading,
    error: t2EchoLatestError,
  } = useFetchLatestQubitTaskGroupedByChip(selectedChip, "CheckT2Echo", {
    query: {
      enabled: Boolean(
        selectedChip &&
          selectedDate === "latest" &&
          selectedParameters.includes("t2_echo"),
      ),
      refetchInterval: selectedDate === "latest" ? 30000 : undefined,
      staleTime: 25000,
    },
  });

  const {
    data: t2EchoHistoricalResponse,
    isLoading: t2EchoHistoricalLoading,
    error: t2EchoHistoricalError,
  } = useFetchHistoricalQubitTaskGroupedByChip(
    selectedChip,
    "CheckT2Echo",
    selectedDate,
    {
      query: {
        enabled: Boolean(
          selectedChip &&
            selectedDate !== "latest" &&
            selectedParameters.includes("t2_echo"),
        ),
        staleTime: 60000,
      },
    },
  );

  // Fetch data for T2*
  const {
    data: t2StarLatestResponse,
    isLoading: t2StarLatestLoading,
    error: t2StarLatestError,
  } = useFetchLatestQubitTaskGroupedByChip(selectedChip, "CheckRamsey", {
    query: {
      enabled: Boolean(
        selectedChip &&
          selectedDate === "latest" &&
          selectedParameters.includes("t2_star"),
      ),
      refetchInterval: selectedDate === "latest" ? 30000 : undefined,
      staleTime: 25000,
    },
  });

  const {
    data: t2StarHistoricalResponse,
    isLoading: t2StarHistoricalLoading,
    error: t2StarHistoricalError,
  } = useFetchHistoricalQubitTaskGroupedByChip(
    selectedChip,
    "CheckRamsey",
    selectedDate,
    {
      query: {
        enabled: Boolean(
          selectedChip &&
            selectedDate !== "latest" &&
            selectedParameters.includes("t2_star"),
        ),
        staleTime: 60000,
      },
    },
  );

  // Primary parameter for single parameter mode
  const primaryParameter = selectedParameters[0] || "t1";
  const taskConfig = TASK_CONFIG[primaryParameter];
  const taskName = taskConfig?.name;
  const taskType = taskConfig?.type;

  // Fetch data for single parameter mode (fidelity)
  const {
    data: primaryLatestResponse,
    isLoading: primaryLatestLoading,
    error: primaryLatestError,
  } = useFetchLatestQubitTaskGroupedByChip(selectedChip, taskName || "", {
    query: {
      enabled: Boolean(
        selectedChip &&
          taskName &&
          taskType === "qubit" &&
          selectedDate === "latest" &&
          selectedParameters.some(p => parameterGroups.fidelity.includes(p)),
      ),
      refetchInterval: selectedDate === "latest" ? 30000 : undefined,
      staleTime: 25000,
    },
  });

  const {
    data: primaryHistoricalResponse,
    isLoading: primaryHistoricalLoading,
    error: primaryHistoricalError,
  } = useFetchHistoricalQubitTaskGroupedByChip(
    selectedChip,
    taskName || "",
    selectedDate,
    {
      query: {
        enabled: Boolean(
          selectedChip &&
            taskName &&
            taskType === "qubit" &&
            selectedDate !== "latest" &&
            selectedParameters.some(p => parameterGroups.fidelity.includes(p)),
        ),
        staleTime: 60000,
      },
    },
  );

  // Fetch data for Gate Fidelity parameters
  const {
    data: gateFidelityLatestResponse,
    isLoading: gateFidelityLatestLoading,
    error: gateFidelityLatestError,
  } = useFetchLatestQubitTaskGroupedByChip(selectedChip, "RandomizedBenchmarking", {
    query: {
      enabled: Boolean(
        selectedChip &&
          selectedDate === "latest" &&
          selectedParameters.includes("gate_fidelity"),
      ),
      refetchInterval: selectedDate === "latest" ? 30000 : undefined,
      staleTime: 25000,
    },
  });

  const {
    data: gateFidelityHistoricalResponse,
    isLoading: gateFidelityHistoricalLoading,
    error: gateFidelityHistoricalError,
  } = useFetchHistoricalQubitTaskGroupedByChip(selectedChip, "RandomizedBenchmarking", selectedDate, {
    query: {
      enabled: Boolean(
        selectedChip &&
          selectedDate !== "latest" &&
          selectedParameters.includes("gate_fidelity"),
      ),
      staleTime: 60000,
    },
  });

  // Fetch data for X90 Fidelity
  const {
    data: x90FidelityLatestResponse,
    isLoading: x90FidelityLatestLoading,
    error: x90FidelityLatestError,
  } = useFetchLatestQubitTaskGroupedByChip(selectedChip, "X90InterleavedRandomizedBenchmarking", {
    query: {
      enabled: Boolean(
        selectedChip &&
          selectedDate === "latest" &&
          selectedParameters.includes("x90_fidelity"),
      ),
      refetchInterval: selectedDate === "latest" ? 30000 : undefined,
      staleTime: 25000,
    },
  });

  const {
    data: x90FidelityHistoricalResponse,
    isLoading: x90FidelityHistoricalLoading,
    error: x90FidelityHistoricalError,
  } = useFetchHistoricalQubitTaskGroupedByChip(selectedChip, "X90InterleavedRandomizedBenchmarking", selectedDate, {
    query: {
      enabled: Boolean(
        selectedChip &&
          selectedDate !== "latest" &&
          selectedParameters.includes("x90_fidelity"),
      ),
      staleTime: 60000,
    },
  });

  // Fetch data for X180 Fidelity
  const {
    data: x180FidelityLatestResponse,
    isLoading: x180FidelityLatestLoading,
    error: x180FidelityLatestError,
  } = useFetchLatestQubitTaskGroupedByChip(selectedChip, "X180InterleavedRandomizedBenchmarking", {
    query: {
      enabled: Boolean(
        selectedChip &&
          selectedDate === "latest" &&
          selectedParameters.includes("x180_fidelity"),
      ),
      refetchInterval: selectedDate === "latest" ? 30000 : undefined,
      staleTime: 25000,
    },
  });

  const {
    data: x180FidelityHistoricalResponse,
    isLoading: x180FidelityHistoricalLoading,
    error: x180FidelityHistoricalError,
  } = useFetchHistoricalQubitTaskGroupedByChip(selectedChip, "X180InterleavedRandomizedBenchmarking", selectedDate, {
    query: {
      enabled: Boolean(
        selectedChip &&
          selectedDate !== "latest" &&
          selectedParameters.includes("x180_fidelity"),
      ),
      staleTime: 60000,
    },
  });

  // Fetch data for Readout Fidelity
  const {
    data: readoutFidelityLatestResponse,
    isLoading: readoutFidelityLatestLoading,
    error: readoutFidelityLatestError,
  } = useFetchLatestQubitTaskGroupedByChip(selectedChip, "ReadoutClassification", {
    query: {
      enabled: Boolean(
        selectedChip &&
          selectedDate === "latest" &&
          selectedParameters.includes("readout_fidelity"),
      ),
      refetchInterval: selectedDate === "latest" ? 30000 : undefined,
      staleTime: 25000,
    },
  });

  const {
    data: readoutFidelityHistoricalResponse,
    isLoading: readoutFidelityHistoricalLoading,
    error: readoutFidelityHistoricalError,
  } = useFetchHistoricalQubitTaskGroupedByChip(selectedChip, "ReadoutClassification", selectedDate, {
    query: {
      enabled: Boolean(
        selectedChip &&
          selectedDate !== "latest" &&
          selectedParameters.includes("readout_fidelity"),
      ),
      staleTime: 60000,
    },
  });

  // Combine loading states
  const isLoading = useMemo(() => {
    const needsCoherenceData = selectedParameters.some(p => parameterGroups.coherence.includes(p));
    const needsFidelityData = selectedParameters.some(p => parameterGroups.fidelity.includes(p));
    
    let isLoadingCoherence = false;
    let isLoadingFidelity = false;
    
    if (needsCoherenceData) {
      if (selectedDate === "latest") {
        isLoadingCoherence = t1LatestLoading || t2EchoLatestLoading || t2StarLatestLoading;
      } else {
        isLoadingCoherence = t1HistoricalLoading || t2EchoHistoricalLoading || t2StarHistoricalLoading;
      }
    }
    
    if (needsFidelityData) {
      if (selectedDate === "latest") {
        isLoadingFidelity = primaryLatestLoading || gateFidelityLatestLoading || x90FidelityLatestLoading || x180FidelityLatestLoading || readoutFidelityLatestLoading;
      } else {
        isLoadingFidelity = primaryHistoricalLoading || gateFidelityHistoricalLoading || x90FidelityHistoricalLoading || x180FidelityHistoricalLoading || readoutFidelityHistoricalLoading;
      }
    }
    
    return isLoadingCoherence || isLoadingFidelity;
  }, [
    selectedParameters,
    selectedDate,
    t1LatestLoading,
    t2EchoLatestLoading,
    t2StarLatestLoading,
    t1HistoricalLoading,
    t2EchoHistoricalLoading,
    t2StarHistoricalLoading,
    gateFidelityLatestLoading,
    x90FidelityLatestLoading,
    x180FidelityLatestLoading,
    readoutFidelityLatestLoading,
    gateFidelityHistoricalLoading,
    x90FidelityHistoricalLoading,
    x180FidelityHistoricalLoading,
    readoutFidelityHistoricalLoading,
  ]);

  // Combine error states
  const error = useMemo(() => {
    const needsCoherenceData = selectedParameters.some(p => parameterGroups.coherence.includes(p));
    const needsFidelityData = selectedParameters.some(p => parameterGroups.fidelity.includes(p));
    
    let coherenceError = null;
    let fidelityError = null;
    
    if (needsCoherenceData) {
      if (selectedDate === "latest") {
        coherenceError = t1LatestError || t2EchoLatestError || t2StarLatestError;
      } else {
        coherenceError = t1HistoricalError || t2EchoHistoricalError || t2StarHistoricalError;
      }
    }
    
    if (needsFidelityData) {
      if (selectedDate === "latest") {
        fidelityError = primaryLatestError || gateFidelityLatestError || x90FidelityLatestError || x180FidelityLatestError || readoutFidelityLatestError;
      } else {
        fidelityError = primaryHistoricalError || gateFidelityHistoricalError || x90FidelityHistoricalError || x180FidelityHistoricalError || readoutFidelityHistoricalError;
      }
    }
    
    return coherenceError || fidelityError;
  }, [
    selectedParameters,
    selectedDate,
    t1LatestError,
    t2EchoLatestError,
    t2StarLatestError,
    t1HistoricalError,
    t2EchoHistoricalError,
    t2StarHistoricalError,
    gateFidelityLatestError,
    x90FidelityLatestError,
    x180FidelityLatestError,
    readoutFidelityLatestError,
    gateFidelityHistoricalError,
    x90FidelityHistoricalError,
    x180FidelityHistoricalError,
    readoutFidelityHistoricalError,
  ]);

  // Helper function to process data for a single parameter
  function processParameterData(
    taskResult: any,
    parameterKey: string,
    outputParamName: string,
  ) {
    if (!taskResult) {
      return {
        plotData: [],
        tableData: [],
        median: null,
        mean: null,
        percentile10: null,
        percentile90: null,
        yieldPercent: null,
        avgR2: null,
        avgError: null,
      };
    }

    // Collect all latest values from each qubit with error information
    const allValues: {
      value: number;
      qid: string;
      error?: number;
      r2?: number;
    }[] = [];

    Object.entries(taskResult).forEach(([qid, taskResultItem]) => {
      const taskResult = taskResultItem as any;
      if (taskResult?.output_parameters) {
        const paramValue = taskResult.output_parameters[outputParamName];

        if (paramValue !== null && paramValue !== undefined) {
          let value: number;

          // Handle different data structures
          if (typeof paramValue === "number") {
            value = paramValue;
          } else if (typeof paramValue === "string") {
            value = Number(paramValue);
          } else if (typeof paramValue === "object" && paramValue !== null) {
            // Handle nested object with value property (e.g., {value: 123, error: 0.1})
            if ("value" in paramValue && typeof paramValue.value === "number") {
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
                `Unknown object structure for ${parameterKey}:`,
                paramValue,
              );
              return;
            }
          } else {
            console.warn(
              `Cannot process value type for ${parameterKey}:`,
              typeof paramValue,
            );
            return;
          }

          // Extract error information if available
          let errorValue: number | undefined = undefined;
          const errorParamName = `${outputParamName}_err`;
          if (
            taskResult.output_parameters[errorParamName] !== null &&
            taskResult.output_parameters[errorParamName] !== undefined
          ) {
            errorValue = Number(taskResult.output_parameters[errorParamName]);
          }

          // Note: R² values are not available in the current API schema
          let r2Value: number | undefined = undefined;

          // Note: API returns fidelity values directly for gate fidelity parameters
          // No conversion needed - use values as-is for fidelity display

          // Data quality filter: reject if value is invalid
          if (!isNaN(value) && value >= 0) {
            allValues.push({ value, qid, error: errorValue, r2: r2Value });
          }
        }
      }
    });

    if (allValues.length === 0) {
      return {
        plotData: [],
        tableData: [],
        median: null,
        mean: null,
        percentile10: null,
        percentile90: null,
        yieldPercent: null,
        avgR2: null,
        avgError: null,
      };
    }

    // Sort values for CDF calculation (always ascending)
    const sortedValues = [...allValues].sort((a, b) => a.value - b.value);

    // Calculate CDF (always ascending from 0 to 1)
    const cdfData: CumulativeDataPoint[] = sortedValues.map((item, index) => ({
      value: item.value,
      error: item.error,
      cdf: (index + 1) / sortedValues.length,
      survivalFunction: 1 - (index + 1) / sortedValues.length,
      qid: item.qid,
      r2: item.r2,
    }));

    // Calculate statistics
    const valuesOnly = sortedValues.map((item) => item.value);
    const medianValue = valuesOnly[Math.floor(valuesOnly.length / 2)];
    const meanValue =
      valuesOnly.reduce((sum, val) => sum + val, 0) / valuesOnly.length;
    const percentile10Value = valuesOnly[Math.floor(valuesOnly.length * 0.1)];
    const percentile90Value = valuesOnly[Math.floor(valuesOnly.length * 0.9)];

    // Calculate average R² and error for quality metrics
    const r2Values = sortedValues
      .filter((item) => item.r2 !== undefined)
      .map((item) => item.r2!);
    const avgR2Value =
      r2Values.length > 0
        ? r2Values.reduce((sum, r2) => sum + r2, 0) / r2Values.length
        : null;

    const errorValues = sortedValues
      .filter((item) => item.error !== undefined)
      .map((item) => item.error!);
    const avgErrorValue =
      errorValues.length > 0
        ? errorValues.reduce((sum, err) => sum + err, 0) / errorValues.length
        : null;

    // Calculate yield based on parameter-specific thresholds (coherence-limited)
    // These thresholds are based on realistic quantum error correction requirements
    const thresholds = {
      t1: 100, // 100µs - minimum for error correction protocols
      t2_echo: 200, // 200µs - echo can extend T2 significantly
      t2_star: 50, // 50µs - dephasing limited
      gate_fidelity: 0.99, // 99% fidelity - threshold for QEC (surface code)
      x90_fidelity: 0.999, // 99.9% fidelity - single qubit gates should be very high
      x180_fidelity: 0.999, // 99.9% fidelity - single qubit gates should be very high
      zx90_fidelity: 0.99, // 99% fidelity - two-qubit gates are typically lower
      readout_fidelity: 0.99, // 99% fidelity - readout should be high for QEC
    };
    const threshold = thresholds[parameterKey as keyof typeof thresholds];
    const paramConfig = PARAMETER_CONFIG[parameterKey];
    const yieldCount = threshold
      ? valuesOnly.filter((v) =>
          paramConfig.higherIsBetter ? v >= threshold : v <= threshold,
        ).length
      : 0;
    const yieldValue = threshold
      ? (yieldCount / valuesOnly.length) * 100
      : null;

    // Always use CDF (ascending from 0 to 1) for consistency
    // Create step plot data for Plotly
    const xValues: number[] = [];
    const yValues: number[] = [];

    // Add steps for proper CDF visualization
    // For step plots, we need to start at CDF=0 and step up at each data point
    cdfData.forEach((point, index) => {
      if (index === 0) {
        // Start from the first value with CDF=0, then step up to the actual CDF
        xValues.push(point.value);
        yValues.push(0);
      }
      
      // Step up to the CDF value at this point
      xValues.push(point.value);
      yValues.push(point.cdf);
    });

    const plotTrace = {
      x: xValues,
      y: yValues,
      type: "scatter" as const,
      mode: "lines" as const,
      line: {
        shape: "hv" as const, // Horizontal-vertical step
        width: 2,
        color: "#3b82f6",
      },
      name: PARAMETER_CONFIG[parameterKey].label,
      hovertemplate:
        "Value: %{x:.4f}<br>" +
        "P(X ≤ value): %{y:.2%}" +
        "<br>" +
        "<extra></extra>",
    };

    // Add median line
    const medianTrace = {
      x: [medianValue, medianValue],
      y: [0, 1],
      type: "scatter" as const,
      mode: "lines" as const,
      line: {
        color: "red",
        width: 2,
        dash: "dash" as const,
      },
      name: `Median: ${medianValue.toFixed(4)}`,
      hovertemplate: "Median: %{x:.4f}<br>" + "<extra></extra>",
    };

    // Add percentile lines
    const p10Trace = {
      x: [percentile10Value, percentile10Value],
      y: [0, 1],
      type: "scatter" as const,
      mode: "lines" as const,
      line: {
        color: "orange",
        width: 1,
        dash: "dot" as const,
      },
      name: `P10: ${percentile10Value.toFixed(4)}`,
      hovertemplate: "10th Percentile: %{x:.4f}<br><extra></extra>",
    };

    const p90Trace = {
      x: [percentile90Value, percentile90Value],
      y: [0, 1],
      type: "scatter" as const,
      mode: "lines" as const,
      line: {
        color: "orange",
        width: 1,
        dash: "dot" as const,
      },
      name: `P90: ${percentile90Value.toFixed(4)}`,
      hovertemplate: "90th Percentile: %{x:.4f}<br><extra></extra>",
    };

    return {
      plotData: [plotTrace, medianTrace, p10Trace, p90Trace],
      tableData: cdfData,
      median: medianValue,
      mean: meanValue,
      percentile10: percentile10Value,
      percentile90: percentile90Value,
      yieldPercent: yieldValue,
      avgR2: avgR2Value,
      avgError: avgErrorValue,
    };
  }

  // Process data for multiple parameters
  const processedDataByParameter = useMemo(() => {
    const results: Record<string, any> = {};

    // Check which parameters need loading  
    const needsCoherenceData = selectedParameters.some(p => parameterGroups.coherence.includes(p));
    if (needsCoherenceData) {
      // Process T1 data
      if (selectedParameters.includes("t1")) {
        const t1Response =
          selectedDate === "latest" ? t1LatestResponse : t1HistoricalResponse;
        if (t1Response?.data?.result) {
          results["t1"] = processParameterData(
            t1Response.data.result,
            "t1",
            OUTPUT_PARAM_NAMES["t1"],
          );
        }
      }

      // Process T2 Echo data
      if (selectedParameters.includes("t2_echo")) {
        const t2EchoResponse =
          selectedDate === "latest"
            ? t2EchoLatestResponse
            : t2EchoHistoricalResponse;
        if (t2EchoResponse?.data?.result) {
          results["t2_echo"] = processParameterData(
            t2EchoResponse.data.result,
            "t2_echo",
            OUTPUT_PARAM_NAMES["t2_echo"],
          );
        }
      }

      // Process T2* data
      if (selectedParameters.includes("t2_star")) {
        const t2StarResponse =
          selectedDate === "latest"
            ? t2StarLatestResponse
            : t2StarHistoricalResponse;
        if (t2StarResponse?.data?.result) {
          results["t2_star"] = processParameterData(
            t2StarResponse.data.result,
            "t2_star",
            OUTPUT_PARAM_NAMES["t2_star"],
          );
        }
      }
    }
    
    // Process gate fidelity parameters if selected
    const hasFidelityParams = selectedParameters.some(p => parameterGroups.fidelity.includes(p));
    if (hasFidelityParams) {
      // Process Gate Fidelity
      if (selectedParameters.includes("gate_fidelity")) {
        const gateFidelityResponse = selectedDate === "latest" ? gateFidelityLatestResponse : gateFidelityHistoricalResponse;
        if (gateFidelityResponse?.data?.result) {
          results["gate_fidelity"] = processParameterData(
            gateFidelityResponse.data.result,
            "gate_fidelity",
            OUTPUT_PARAM_NAMES["gate_fidelity"],
          );
        }
      }
      
      // Process X90 Fidelity
      if (selectedParameters.includes("x90_fidelity")) {
        const x90FidelityResponse = selectedDate === "latest" ? x90FidelityLatestResponse : x90FidelityHistoricalResponse;
        if (x90FidelityResponse?.data?.result) {
          results["x90_fidelity"] = processParameterData(
            x90FidelityResponse.data.result,
            "x90_fidelity",
            OUTPUT_PARAM_NAMES["x90_fidelity"],
          );
        }
      }
      
      // Process X180 Fidelity
      if (selectedParameters.includes("x180_fidelity")) {
        const x180FidelityResponse = selectedDate === "latest" ? x180FidelityLatestResponse : x180FidelityHistoricalResponse;
        if (x180FidelityResponse?.data?.result) {
          results["x180_fidelity"] = processParameterData(
            x180FidelityResponse.data.result,
            "x180_fidelity",
            OUTPUT_PARAM_NAMES["x180_fidelity"],
          );
        }
      }
      
      // Process Readout Fidelity
      if (selectedParameters.includes("readout_fidelity")) {
        const readoutFidelityResponse = selectedDate === "latest" ? readoutFidelityLatestResponse : readoutFidelityHistoricalResponse;
        if (readoutFidelityResponse?.data?.result) {
          results["readout_fidelity"] = processParameterData(
            readoutFidelityResponse.data.result,
            "readout_fidelity",
            OUTPUT_PARAM_NAMES["readout_fidelity"],
          );
        }
      }
    }

    return results;
  }, [
    selectedParameters,
    selectedDate,
    t1LatestResponse,
    t1HistoricalResponse,
    t2EchoLatestResponse,
    t2EchoHistoricalResponse,
    t2StarLatestResponse,
    t2StarHistoricalResponse,
    gateFidelityLatestResponse,
    gateFidelityHistoricalResponse,
    x90FidelityLatestResponse,
    x90FidelityHistoricalResponse,
    x180FidelityLatestResponse,
    x180FidelityHistoricalResponse,
    readoutFidelityLatestResponse,
    readoutFidelityHistoricalResponse,
    primaryLatestResponse,
    primaryHistoricalResponse,
    primaryParameter,
  ]);

  // Apply conversion for fidelity parameters based on display mode
  const displayDataByParameter = useMemo(() => {
    if (currentParameterType !== "fidelity") {
      return processedDataByParameter;
    }

    const convertedData: Record<string, any> = {};
    
    Object.entries(processedDataByParameter).forEach(([param, data]) => {
      if (parameterGroups.fidelity.includes(param) && data) {
        let conversionFactor;
        if (showAsErrorRate) {
          // Convert fidelity to error rate percentage: (1 - fidelity) * 100
          conversionFactor = (val: number) => (1 - val) * 100;
        } else {
          // Convert fidelity to fidelity percentage: fidelity * 100
          conversionFactor = (val: number) => val * 100;
        }

        const convertedPlotData = data.plotData?.map((trace: any) => {
          if (showAsErrorRate) {
            // For error rate mode: reverse only X axis
            // Original: fidelity ascending (low -> high), CDF ascending 0->1
            // After conversion: error rate descending (high -> low)
            // Reverse X only: error rate ascending (low -> high), keep CDF ascending 0->1
            const convertedX = trace.x?.map(conversionFactor);
            
            return {
              ...trace,
              x: convertedX?.slice().reverse(), // Reverse to get ascending error rate order  
              y: trace.y, // Keep original CDF direction (0->1)
            };
          } else {
            return {
              ...trace,
              x: trace.x?.map(conversionFactor),
            };
          }
        });

        const convertedTableData = data.tableData?.map((item: any) => ({
          ...item,
          value: conversionFactor(item.value),
        }));

        convertedData[param] = {
          ...data,
          plotData: convertedPlotData,
          tableData: convertedTableData,
          median: data.median ? conversionFactor(data.median) : null,
          mean: data.mean ? conversionFactor(data.mean) : null,
          percentile10: data.percentile10 ? conversionFactor(data.percentile10) : null,
          percentile90: data.percentile90 ? conversionFactor(data.percentile90) : null,
        };
      } else {
        convertedData[param] = data;
      }
    });

    return convertedData;
  }, [processedDataByParameter, showAsErrorRate, currentParameterType, parameterGroups]);

  // Get data for the primary parameter (for backwards compatibility)
  const primaryData = displayDataByParameter[primaryParameter] || {
    plotData: [],
    tableData: [],
    median: null,
    mean: null,
    percentile10: null,
    percentile90: null,
    yieldPercent: null,
    avgR2: null,
    avgError: null,
  };

  const { plotData, tableData } = primaryData;

  // CSV Export
  const { exportToCSV } = useCSVExport();

  const handleExportCSV = () => {
    if (tableData.length === 0) return;

    const headers = [
      "Entity_ID",
      "Value",
      "Error",
      "CDF",
      "Survival_Function",
      "R_squared",
      "Parameter",
      "Task",
      "Entity_Type",
      "Timestamp",
    ];
    const timestamp = new Date().toISOString();
    const rows = tableData.map((row: CumulativeDataPoint) => [
      row.qid,
      String(row.value.toFixed(6)),
      row.error !== undefined ? String(row.error.toFixed(6)) : "N/A",
      String(row.cdf.toFixed(6)),
      String(row.survivalFunction.toFixed(6)),
      row.r2 !== undefined ? String(row.r2.toFixed(6)) : "N/A",
      primaryParameter,
      taskName,
      taskType === "coupling" ? "coupling_pair" : "qubit",
      timestamp,
    ]);

    const dateStr = selectedDate === "latest" ? "latest" : selectedDate;
    const filename = `cumulative_${primaryParameter}_${selectedChip}_${dateStr}_${timestamp.slice(0, 19).replace(/[:-]/g, "")}.csv`;

    exportToCSV({ filename, headers, data: rows });
  };


  // Create combined plot data when multiple parameters are selected
  const combinedPlotData = useMemo(() => {
    if (selectedParameters.length > 1) {
      // Color palette for multiple parameters
      const colors = {
        t1: "#3b82f6",           // blue
        t2_echo: "#f97316",       // orange  
        t2_star: "#10b981",       // green
        gate_fidelity: "#ef4444", // red
        x90_fidelity: "#8b5cf6",  // violet
        x180_fidelity: "#f59e0b", // amber
        readout_fidelity: "#06b6d4" // cyan
      };
      
      return selectedParameters.flatMap((param) => {
        const data = displayDataByParameter[param];
        if (!data || !data.plotData || data.plotData.length === 0) return [];
        
        // Modify colors for each trace
        return data.plotData.map((trace: any, idx: number) => {
          if (idx === 0) {
            // Main trace
            return {
              ...trace,
              line: {
                ...trace.line,
                color: colors[param as keyof typeof colors] || "#6b7280",
              },
              name: PARAMETER_CONFIG[param].label,
            };
          } else if (idx === 1) {
            // Median line
            const unit = parameterGroups.coherence.includes(param) 
              ? " µs" 
              : parameterGroups.fidelity.includes(param) && !showAsErrorRate
                ? "%" 
                : "";
            return {
              ...trace,
              line: {
                ...trace.line,
                color: colors[param as keyof typeof colors] || "#6b7280",
                dash: "dash",
              },
              name: `${PARAMETER_CONFIG[param].label} median: ${showAsErrorRate && parameterGroups.fidelity.includes(param) ? data.median?.toExponential(1) : data.median?.toFixed(parameterGroups.coherence.includes(param) ? 2 : 2)}${unit}`,
              showlegend: true,
            };
          } else {
            return { ...trace, showlegend: false }; // Hide percentile lines in legend
          }
        });
      });
    }

    // For single parameter, use the primary parameter data
    return plotData;
  }, [selectedParameters, displayDataByParameter, plotData, parameterGroups]);

  // Determine plot characteristics based on selected parameters
  const hasCoherenceParams = selectedParameters.some(p => parameterGroups.coherence.includes(p));
  const hasFidelityParams = selectedParameters.some(p => parameterGroups.fidelity.includes(p));
  const isMixedParams = hasCoherenceParams && hasFidelityParams;
  
  const layout = {
    title: {
      text: isMixedParams 
        ? `Cumulative Distribution - Selected Parameters`
        : hasCoherenceParams 
          ? "Cumulative Distribution - Coherence Times"
          : hasFidelityParams
            ? "Cumulative Distribution - Gate Fidelities"
            : "Cumulative Distribution",
      font: { size: 18 },
    },
    xaxis: {
      title: isMixedParams
        ? "Parameter Value"
        : hasCoherenceParams
          ? "Coherence Time (µs)"
          : hasFidelityParams
            ? (showAsErrorRate ? "Gate Error Rate (%)" : "Gate Fidelity (%)")
            : "Value",
      gridcolor: "#e5e7eb",
      showgrid: true,
      zeroline: false,
      type: hasFidelityParams ? ("log" as const) : ("linear" as const),
      tickformat: hasFidelityParams 
        ? (showAsErrorRate ? ".1e" : ".2f") 
        : undefined,
      exponentformat: hasFidelityParams && showAsErrorRate ? ("power" as const) : undefined,
      nticks: hasFidelityParams ? 6 : undefined, // Reduce number of ticks to prevent overlap
    },
    yaxis: {
      title: "Cumulative Probability P(X ≤ value)",
      gridcolor: "#e5e7eb",
      showgrid: true,
      zeroline: false,
      range: [0, 1],
    },
    hovermode: "closest" as const,
    showlegend: true,
    legend: {
      x: 0.02,
      y: 0.98,
      bgcolor: "rgba(255, 255, 255, 0.8)",
      bordercolor: "#e5e7eb",
      borderwidth: 1,
    },
    margin: { t: 60, r: 50, b: 50, l: 80 },
    plot_bgcolor: "#ffffff",
    paper_bgcolor: "#ffffff",
    annotations: displayDataByParameter[primaryParameter]?.tableData
      ? [
          {
            text: `Data snapshot: ${selectedDate === "latest" ? "Latest calibration" : `Date: ${formatDate(selectedDate)}`}<br>Sample size: ${displayDataByParameter[primaryParameter].tableData.length} qubits`,
            showarrow: false,
            xref: "paper" as const,
            yref: "paper" as const,
            x: 0.02,
            y: -0.15,
            xanchor: "left" as const,
            yanchor: "top" as const,
            font: { size: 11, color: "#666" },
          },
        ]
      : [],
  };

  if (error) {
    return (
      <ErrorCard
        title="Failed to load cumulative data"
        message={error.message || "An unexpected error occurred"}
        onRetry={() => window.location.reload()}
      />
    );
  }

  return (
    <div className="space-y-6">
      {/* Controls Section */}
      <div className="card bg-base-100 shadow-md">
        <div className="card-body">
          <div className="flex flex-wrap items-end gap-4">
            {/* Chip Selection */}
            <div className="form-control min-w-48">
              <label className="label h-8">
                <span className="label-text font-semibold">Chip</span>
              </label>
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

            {/* Parameter Selection with multi-select */}
            <div className="form-control min-w-80">
              <div className="flex justify-between items-center h-8">
                <span className="label-text font-semibold">Parameters</span>
                <span className="text-xs text-gray-500">
                  Select parameters to compare
                </span>
              </div>
              <div className="h-10">
                <Select<{ value: string; label: string }, true>
                  isMulti
                  options={availableParameters}
                  value={(() => {
                    // Handle different structures based on parameter type
                    if (currentParameterType && Array.isArray(availableParameters)) {
                      // Single type selected - flat array
                      return availableParameters.filter((option: any) =>
                        selectedParameters.includes(option.value)
                      );
                    } else if (Array.isArray(availableParameters)) {
                      // No type selected yet - grouped array
                      return availableParameters.flatMap((group: any) => group.options || []).filter((option: any) =>
                        selectedParameters.includes(option.value)
                      );
                    }
                    return [];
                  })()}
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

            {/* Display Format Toggle - Only show for fidelity parameters */}
            {currentParameterType === "fidelity" && (
              <div className="form-control min-w-48">
                <div className="flex justify-between items-center h-8">
                  <span className="label-text font-semibold">Display Format</span>
                </div>
                <div className="h-10 flex items-center">
                  <label className="cursor-pointer label flex items-center gap-2">
                    <span className="text-sm">Fidelity %</span>
                    <input
                      type="checkbox"
                      className="toggle toggle-primary"
                      checked={showAsErrorRate}
                      onChange={(e) => setShowAsErrorRate(e.target.checked)}
                    />
                    <span className="text-sm">Error Rate %</span>
                  </label>
                </div>
              </div>
            )}

            {/* Action Buttons */}
            <div className="form-control min-w-32">
              <label className="label h-8">
                <span className="label-text font-semibold">Export</span>
              </label>
              <div className="h-10">
                <button
                  className="btn btn-outline btn-sm h-full w-full"
                  onClick={handleExportCSV}
                  disabled={tableData.length === 0}
                >
                  Export CSV
                </button>
              </div>
            </div>
          </div>

          {/* Statistics Display - Multi-parameter support */}
          {selectedParameters.length > 0 && (
            <div className="mt-4 space-y-4">
              {selectedParameters.map((param) => {
                const data = displayDataByParameter[param];
                if (!data || data.median === null) return null;

                const colors = {
                  t1: "text-blue-600",
                  t2_echo: "text-orange-600", 
                  t2_star: "text-green-600",
                  gate_fidelity: "text-red-600",
                  x90_fidelity: "text-violet-600",
                  x180_fidelity: "text-amber-600",
                  readout_fidelity: "text-cyan-600"
                };

                const unit = parameterGroups.coherence.includes(param) 
                  ? " µs" 
                  : parameterGroups.fidelity.includes(param) && !showAsErrorRate
                    ? "%" 
                    : "";
                const colorClass = colors[param as keyof typeof colors] || "text-gray-600";
                
                // Format numbers based on display mode
                const formatValue = (value: number) => {
                  if (parameterGroups.coherence.includes(param)) {
                    return value.toFixed(2);
                  } else if (parameterGroups.fidelity.includes(param) && showAsErrorRate) {
                    return value.toExponential(1); // Scientific notation for error rates
                  } else {
                    return value.toFixed(2);
                  }
                };

                return (
                  <div key={param} className="stats shadow grid-cols-2 lg:grid-cols-6 xl:grid-cols-7">
                    <div className="stat">
                      <div className="stat-title">Parameter</div>
                      <div className={`stat-value text-sm ${colorClass}`}>
                        {PARAMETER_CONFIG[param].label}
                      </div>
                    </div>
                    <div className="stat">
                      <div className="stat-title">N_valid</div>
                      <div className="stat-value text-success text-sm">
                        {data.tableData.length}
                      </div>
                    </div>
                    <div className="stat">
                      <div className="stat-title">Median</div>
                      <div className="stat-value text-primary text-sm">
                        {formatValue(data.median)}{unit}
                      </div>
                    </div>
                    <div className="stat">
                      <div className="stat-title">Mean</div>
                      <div className="stat-value text-secondary text-sm">
                        {formatValue(data.mean)}{unit}
                      </div>
                    </div>
                    <div className="stat">
                      <div className="stat-title">10th %ile</div>
                      <div className="stat-value text-accent text-sm">
                        {formatValue(data.percentile10!)}{unit}
                      </div>
                    </div>
                    <div className="stat">
                      <div className="stat-title">90th %ile</div>
                      <div className="stat-value text-accent text-sm">
                        {formatValue(data.percentile90!)}{unit}
                      </div>
                    </div>
                    {data.yieldPercent !== null && (
                      <div className="stat">
                        <div className="stat-title">Yield</div>
                        <div className="stat-value text-success text-sm">
                          {data.yieldPercent.toFixed(1)}%
                        </div>
                        <div className="stat-desc">Above threshold</div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>

      {/* Plot Section */}
      <PlotCard
        plotData={combinedPlotData}
        layout={layout}
        isLoading={isLoading}
        title="Cumulative Distribution Function"
      />

      {/* Data Table */}
      <div className="card bg-base-100 shadow-md">
        <div className="card-body">
          <DataTable
            title="Data Points"
            data={tableData}
            columns={[
              { key: "qid", label: "Qubit ID", sortable: true },
              {
                key: "value",
                label: "Value",
                sortable: true,
                render: (v: number, row: CumulativeDataPoint) => {
                  const errorStr =
                    row.error !== undefined ? ` ± ${row.error.toFixed(6)}` : "";
                  return `${v.toFixed(6)}${errorStr}`;
                },
              },
              {
                key: "cdf",
                label: "CDF",
                sortable: true,
                render: (v: number) => (v * 100).toFixed(2) + "%",
              },
              {
                key: "survivalFunction",
                label: "Survival",
                sortable: true,
                render: (v: number) => (v * 100).toFixed(2) + "%",
              },
              {
                key: "r2",
                label: "R²",
                sortable: true,
                render: (v: number | undefined) =>
                  v !== undefined ? v.toFixed(3) : "N/A",
              },
            ]}
            pageSize={10}
          />
        </div>
      </div>
    </div>
  );
}
