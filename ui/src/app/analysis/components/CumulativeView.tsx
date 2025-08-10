"use client";

import { useState, useMemo, useEffect } from "react";
import { useListChips, useFetchLatestQubitTaskGroupedByChip, useFetchLatestCouplingTaskGroupedByChip, useFetchHistoricalQubitTaskGroupedByChip, useFetchHistoricalCouplingTaskGroupedByChip } from "@/client/chip/chip";
import { PlotCard } from "@/shared/components/PlotCard";
import { ErrorCard } from "@/shared/components/ErrorCard";
import { DataTable } from "@/shared/components/DataTable";
import { useCSVExport } from "@/shared/hooks/useCSVExport";
import { ChipSelector } from "@/app/components/ChipSelector";
import { DateSelector } from "@/app/components/DateSelector";
import { useDateNavigation } from "@/app/hooks/useDateNavigation";
import Select, { SingleValue } from "react-select";

// Task names and types mapping
const TASK_CONFIG: Record<string, { name: string; type: 'qubit' | 'coupling' }> = {
  t1: { name: "CheckT1", type: "qubit" },
  t2_echo: { name: "CheckT2Echo", type: "qubit" }, 
  t2_star: { name: "CheckRamsey", type: "qubit" },
  gate_fidelity: { name: "RandomizedBenchmarking", type: "qubit" },
  x90_fidelity: { name: "X90InterleavedRandomizedBenchmarking", type: "qubit" },
  x180_fidelity: { name: "X180InterleavedRandomizedBenchmarking", type: "qubit" },
  zx90_fidelity: { name: "ZX90InterleavedRandomizedBenchmarking", type: "coupling" },
  readout_fidelity: { name: "ReadoutClassification", type: "qubit" },
};

// Parameter configuration: labels and directionality
const PARAMETER_CONFIG: Record<string, { 
  label: string; 
  higherIsBetter: boolean;
  unit: string;
  displayUnit: string;
}> = {
  t1: { label: "T1 Coherence", higherIsBetter: true, unit: "µs", displayUnit: "µs" },
  t2_echo: { label: "T2 Echo", higherIsBetter: true, unit: "µs", displayUnit: "µs" },
  t2_star: { label: "T2 Star", higherIsBetter: true, unit: "µs", displayUnit: "µs" },
  gate_fidelity: { label: "Gate Fidelity (Clifford RB)", higherIsBetter: true, unit: "fidelity", displayUnit: "fidelity" },
  x90_fidelity: { label: "X90 Gate Fidelity", higherIsBetter: true, unit: "fidelity", displayUnit: "fidelity" },
  x180_fidelity: { label: "X180 Gate Fidelity", higherIsBetter: true, unit: "fidelity", displayUnit: "fidelity" },
  zx90_fidelity: { label: "ZX90 Gate Fidelity (2Q)", higherIsBetter: true, unit: "fidelity", displayUnit: "fidelity" },
  readout_fidelity: { label: "Readout Fidelity", higherIsBetter: true, unit: "fidelity", displayUnit: "fidelity" },
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
  const [selectedParameter, setSelectedParameter] = useState<string>("t1");
  const [selectedDate, setSelectedDate] = useState<string>("latest");

  // Available parameters for the cumulative distribution analysis
  // Map parameter keys to human-readable labels for the selector
  const availableParameters = Object.keys(TASK_CONFIG).map(key => ({
    value: key,
    label: PARAMETER_CONFIG[key].label
  }));

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

  const taskConfig = TASK_CONFIG[selectedParameter];
  const taskName = taskConfig?.name;
  const taskType = taskConfig?.type;
  const outputParamName = OUTPUT_PARAM_NAMES[selectedParameter];

  // Fetch calibration data for qubits (latest or date-specific)
  const {
    data: latestQubitTaskResponse,
    isLoading: isLoadingLatestQubit,
    error: errorLatestQubit,
  } = useFetchLatestQubitTaskGroupedByChip(
    selectedChip,
    taskName || "",
    {
      query: {
        enabled: Boolean(selectedChip && taskName && taskType === 'qubit' && selectedDate === 'latest'),
        refetchInterval: selectedDate === 'latest' ? 30000 : undefined,
        staleTime: 25000,
      },
    }
  );

  const {
    data: dateQubitTaskResponse,
    isLoading: isLoadingDateQubit,
    error: errorDateQubit,
  } = useFetchHistoricalQubitTaskGroupedByChip(
    selectedChip,
    taskName || "",
    selectedDate,
    {
      query: {
        enabled: Boolean(selectedChip && taskName && taskType === 'qubit' && selectedDate !== 'latest'),
        staleTime: 60000, // Historical data can be cached longer
      },
    }
  );

  // Fetch calibration data for couplings (latest or date-specific)
  const {
    data: latestCouplingTaskResponse,
    isLoading: isLoadingLatestCoupling,
    error: errorLatestCoupling,
  } = useFetchLatestCouplingTaskGroupedByChip(
    selectedChip,
    taskName || "",
    {
      query: {
        enabled: Boolean(selectedChip && taskName && taskType === 'coupling' && selectedDate === 'latest'),
        refetchInterval: selectedDate === 'latest' ? 30000 : undefined,
        staleTime: 25000,
      },
    }
  );

  const {
    data: dateCouplingTaskResponse,
    isLoading: isLoadingDateCoupling,
    error: errorDateCoupling,
  } = useFetchHistoricalCouplingTaskGroupedByChip(
    selectedChip,
    taskName || "",
    selectedDate,
    {
      query: {
        enabled: Boolean(selectedChip && taskName && taskType === 'coupling' && selectedDate !== 'latest'),
        staleTime: 60000, // Historical data can be cached longer
      },
    }
  );

  // Combine responses and states based on selected date
  const taskResponse = useMemo(() => {
    if (selectedDate === 'latest') {
      return taskType === 'qubit' ? latestQubitTaskResponse : latestCouplingTaskResponse;
    } else {
      return taskType === 'qubit' ? dateQubitTaskResponse : dateCouplingTaskResponse;
    }
  }, [selectedDate, taskType, latestQubitTaskResponse, latestCouplingTaskResponse, dateQubitTaskResponse, dateCouplingTaskResponse]);

  const isLoading = useMemo(() => {
    if (selectedDate === 'latest') {
      return taskType === 'qubit' ? isLoadingLatestQubit : isLoadingLatestCoupling;
    } else {
      return taskType === 'qubit' ? isLoadingDateQubit : isLoadingDateCoupling;
    }
  }, [selectedDate, taskType, isLoadingLatestQubit, isLoadingLatestCoupling, isLoadingDateQubit, isLoadingDateCoupling]);

  const error = useMemo(() => {
    if (selectedDate === 'latest') {
      return taskType === 'qubit' ? errorLatestQubit : errorLatestCoupling;
    } else {
      return taskType === 'qubit' ? errorDateQubit : errorDateCoupling;
    }
  }, [selectedDate, taskType, errorLatestQubit, errorLatestCoupling, errorDateQubit, errorDateCoupling]);


  // Show error if task name is not found
  if (!taskName && selectedParameter) {
    return (
      <ErrorCard
        title="Task Not Available"
        message={`No calibration task found for parameter: ${selectedParameter}`}
        onRetry={() => {}}
      />
    );
  }

  // Process data for cumulative distribution
  const { plotData, tableData, median, mean, percentile10, percentile90, yieldPercent, avgR2, avgError } = useMemo(() => {
    // Debug logging for CumulativeView
    console.log('CumulativeView Debug:', {
      selectedChip,
      selectedParameter,
      selectedDate,
      taskName,
      taskType,
      outputParamName,
      hasTaskResponse: !!taskResponse,
      hasData: !!taskResponse?.data,
      hasResult: !!taskResponse?.data?.result,
      resultKeys: taskResponse?.data?.result ? Object.keys(taskResponse.data.result) : [],
      sampleResult: taskResponse?.data?.result ? Object.entries(taskResponse.data.result).slice(0, 2) : []
    });

    if (!taskResponse?.data?.result) {
      return { plotData: [], tableData: [], median: null, mean: null, percentile10: null, percentile90: null, yieldPercent: null, avgR2: null, avgError: null };
    }

    // Collect all latest values from each qubit with error information
    const allValues: { value: number; qid: string; error?: number; r2?: number }[] = [];
    
    Object.entries(taskResponse.data.result).forEach(([qid, taskResult]) => {
      if (taskResult?.output_parameters) {
        const paramValue = taskResult.output_parameters[outputParamName];
        
        // Debug each parameter value
        console.log(`CumulativeView Debug ${qid}:`, {
          outputParamName,
          paramValue,
          valueType: typeof paramValue,
          hasOutputParams: !!taskResult?.output_parameters,
          outputParamKeys: Object.keys(taskResult.output_parameters)
        });
        
        if (paramValue !== null && paramValue !== undefined) {
          let value: number;
          
          // Handle different data structures
          if (typeof paramValue === 'number') {
            value = paramValue;
          } else if (typeof paramValue === 'string') {
            value = Number(paramValue);
          } else if (typeof paramValue === 'object' && paramValue !== null) {
            // Handle nested object with value property (e.g., {value: 123, error: 0.1})
            if ('value' in paramValue && typeof paramValue.value === 'number') {
              value = paramValue.value;
            } else if ('mean' in paramValue && typeof paramValue.mean === 'number') {
              value = paramValue.mean;
            } else if ('result' in paramValue && typeof paramValue.result === 'number') {
              value = paramValue.result;
            } else {
              console.warn(`Unknown object structure for ${selectedParameter}:`, paramValue);
              return;
            }
          } else {
            console.warn(`Cannot process value type for ${selectedParameter}:`, typeof paramValue);
            return;
          }
          
          // Extract error information if available
          let errorValue: number | undefined = undefined;
          const errorParamName = `${outputParamName}_err`;
          if (taskResult.output_parameters[errorParamName] !== null && 
              taskResult.output_parameters[errorParamName] !== undefined) {
            errorValue = Number(taskResult.output_parameters[errorParamName]);
          }
          
          // Note: R² values are not available in the current API schema
          let r2Value: number | undefined = undefined;
          
          // No unit conversion needed - data is already in correct units
          // Note: We keep fidelities as-is (higher is better) for proper survival function
          
          // Data quality filter: reject if value is invalid
          if (!isNaN(value) && value > 0) {
            allValues.push({ value, qid, error: errorValue, r2: r2Value });
          }
        }
      }
    });

    if (allValues.length === 0) {
      return { plotData: [], tableData: [], median: null, mean: null, percentile10: null, percentile90: null, yieldPercent: null, avgR2: null, avgError: null };
    }

    // Sort values for CDF calculation
    const sortedValues = [...allValues].sort((a, b) => a.value - b.value);
    
    // Calculate CDF and survival function
    const cdfData: CumulativeDataPoint[] = sortedValues.map((item, index) => ({
      value: item.value,
      error: item.error,
      cdf: (index + 1) / sortedValues.length,
      survivalFunction: 1 - (index + 1) / sortedValues.length,
      qid: item.qid,
      r2: item.r2,
    }));

    // Calculate statistics
    const valuesOnly = sortedValues.map(item => item.value);
    const medianValue = valuesOnly[Math.floor(valuesOnly.length / 2)];
    const meanValue = valuesOnly.reduce((sum, val) => sum + val, 0) / valuesOnly.length;
    const percentile10Value = valuesOnly[Math.floor(valuesOnly.length * 0.1)];
    const percentile90Value = valuesOnly[Math.floor(valuesOnly.length * 0.9)];
    
    // Calculate average R² and error for quality metrics
    const r2Values = sortedValues.filter(item => item.r2 !== undefined).map(item => item.r2!);
    const avgR2Value = r2Values.length > 0 ? r2Values.reduce((sum, r2) => sum + r2, 0) / r2Values.length : null;
    
    const errorValues = sortedValues.filter(item => item.error !== undefined).map(item => item.error!);
    const avgErrorValue = errorValues.length > 0 ? errorValues.reduce((sum, err) => sum + err, 0) / errorValues.length : null;
    
    // Calculate yield based on parameter-specific thresholds (coherence-limited)
    // These thresholds are based on realistic quantum error correction requirements
    const thresholds = {
      t1: 100, // 100µs - minimum for error correction protocols
      t2_echo: 200, // 200µs - echo can extend T2 significantly  
      t2_star: 50, // 50µs - dephasing limited
      gate_fidelity: 0.999, // 99.9% - threshold for QEC (surface code)
      x90_fidelity: 0.9999, // 99.99% - single qubit gates should be very high
      x180_fidelity: 0.9999, // 99.99% - single qubit gates should be very high
      zx90_fidelity: 0.99, // 99% - two-qubit gates are typically lower
      readout_fidelity: 0.99, // 99% - readout should be high for QEC
    };
    const threshold = thresholds[selectedParameter as keyof typeof thresholds];
    const paramConfig = PARAMETER_CONFIG[selectedParameter];
    const yieldCount = threshold ? valuesOnly.filter(v => 
      paramConfig.higherIsBetter ? v >= threshold : v <= threshold
    ).length : 0;
    const yieldValue = threshold ? (yieldCount / valuesOnly.length) * 100 : null;

    // Use survival function for "higher is better" metrics, CDF for "lower is better"
    const useSurvival = paramConfig.higherIsBetter;
    
    // Create step plot data for Plotly  
    const xValues: number[] = [];
    const yValues: number[] = [];
    
    // Add starting point
    if (cdfData.length > 0) {
      xValues.push(cdfData[0].value);
      yValues.push(useSurvival ? 1 : 0);
    }
    
    // Add steps
    cdfData.forEach((point) => {
      xValues.push(point.value);
      yValues.push(useSurvival ? point.survivalFunction : point.cdf);
    });

    const plotTrace = {
      x: xValues,
      y: yValues,
      type: 'scatter' as const,
      mode: 'lines' as const,
      line: {
        shape: 'hv' as const, // Horizontal-vertical step
        width: 2,
        color: '#3b82f6',
      },
      name: PARAMETER_CONFIG[selectedParameter].label,
      hovertemplate: 
        'Value: %{x:.4f}<br>' +
        (useSurvival ? 'P(X ≥ value): %{y:.2%}' : 'P(X ≤ value): %{y:.2%}') + '<br>' +
        '<extra></extra>',
    };

    // Add median line
    const medianTrace = {
      x: [medianValue, medianValue],
      y: [0, 1],
      type: 'scatter' as const,
      mode: 'lines' as const,
      line: {
        color: 'red',
        width: 2,
        dash: 'dash' as const,
      },
      name: `Median: ${medianValue.toFixed(4)}`,
      hovertemplate: 
        'Median: %{x:.4f}<br>' +
        '<extra></extra>',
    };

    // Add percentile lines
    const p10Trace = {
      x: [percentile10Value, percentile10Value],
      y: [0, 1],
      type: 'scatter' as const,
      mode: 'lines' as const,
      line: {
        color: 'orange',
        width: 1,
        dash: 'dot' as const,
      },
      name: `P10: ${percentile10Value.toFixed(4)}`,
      hovertemplate: '10th Percentile: %{x:.4f}<br><extra></extra>',
    };

    const p90Trace = {
      x: [percentile90Value, percentile90Value],
      y: [0, 1],
      type: 'scatter' as const,
      mode: 'lines' as const,
      line: {
        color: 'orange',
        width: 1,
        dash: 'dot' as const,
      },
      name: `P90: ${percentile90Value.toFixed(4)}`,
      hovertemplate: '90th Percentile: %{x:.4f}<br><extra></extra>',
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
  }, [taskResponse?.data?.result, selectedParameter, outputParamName]);

  // CSV Export
  const { exportToCSV } = useCSVExport();
  
  const handleExportCSV = () => {
    if (tableData.length === 0) return;
    
    const headers = [
      'Entity_ID', 'Value', 'Error', 'CDF', 'Survival_Function', 
      'R_squared', 'Parameter', 'Task', 'Entity_Type', 'Timestamp'
    ];
    const timestamp = new Date().toISOString();
    const rows = tableData.map(row => [
      row.qid,
      String(row.value.toFixed(6)),
      row.error !== undefined ? String(row.error.toFixed(6)) : 'N/A',
      String(row.cdf.toFixed(6)),
      String(row.survivalFunction.toFixed(6)),
      row.r2 !== undefined ? String(row.r2.toFixed(6)) : 'N/A',
      selectedParameter,
      taskName,
      taskType === 'coupling' ? 'coupling_pair' : 'qubit',
      timestamp,
    ]);
    
    const dateStr = selectedDate === 'latest' ? 'latest' : selectedDate;
    const filename = `cumulative_${selectedParameter}_${selectedChip}_${dateStr}_${timestamp.slice(0, 19).replace(/[:-]/g, '')}.csv`;
    
    exportToCSV({ filename, headers, data: rows });
  };

  // Get parameter configuration for display  
  const currentParamConfig = PARAMETER_CONFIG[selectedParameter];
  const useSurvivalFunction = currentParamConfig.higherIsBetter;

  const layout = {
    title: {
      text: `${useSurvivalFunction ? 'Survival Function' : 'Cumulative Distribution Function'} - ${currentParamConfig.label}`,
      font: { size: 18 },
    },
    xaxis: {
      title: `${currentParamConfig.label}${currentParamConfig.displayUnit !== 'fidelity' ? ` (${currentParamConfig.displayUnit})` : ''}`,
      gridcolor: '#e5e7eb',
      showgrid: true,
      zeroline: false,
      // Use log scale for fidelity metrics when showing as error rates
      ...(currentParamConfig.unit === 'fidelity' && !useSurvivalFunction && { type: 'log' as const }),
    },
    yaxis: {
      title: useSurvivalFunction ? 'P(X ≥ value)' : 'P(X ≤ value)',
      gridcolor: '#e5e7eb',
      showgrid: true,
      zeroline: false,
      range: [0, 1],
    },
    hovermode: 'closest' as const,
    showlegend: true,
    legend: {
      x: 0.02,
      y: 0.98,
      bgcolor: 'rgba(255, 255, 255, 0.8)',
      bordercolor: '#e5e7eb',
      borderwidth: 1,
    },
    margin: { t: 60, r: 50, b: 50, l: 80 },
    plot_bgcolor: '#ffffff',
    paper_bgcolor: '#ffffff',
    annotations: taskResponse?.data ? [{
      text: `Data snapshot: ${selectedDate === 'latest' ? 'Latest calibration' : `Date: ${formatDate(selectedDate)}`}<br>Sample size: ${Object.keys(taskResponse.data.result).length} ${taskType === 'coupling' ? 'coupling pairs' : 'qubits'}`,
      showarrow: false,
      xref: 'paper' as const,
      yref: 'paper' as const,
      x: 0.02,
      y: -0.15,
      xanchor: 'left' as const,
      yanchor: 'top' as const,
      font: { size: 11, color: '#666' }
    }] : [],
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

            {/* Parameter Selection */}
            <div className="form-control min-w-64">
              <div className="flex justify-between items-center h-8">
                <span className="label-text font-semibold">Parameter</span>
                {currentParamConfig.label && (
                  <span className="text-xs text-gray-500">
                    {useSurvivalFunction ? 'Survival Function (P(X ≥ value))' : 'CDF (P(X ≤ value))'}
                  </span>
                )}
              </div>
              <div className="h-10">
                <Select<{ value: string; label: string }>
                  options={availableParameters}
                  value={availableParameters.find(option => option.value === selectedParameter)}
                  onChange={(option: SingleValue<{ value: string; label: string }>) => {
                    if (option) {
                      setSelectedParameter(option.value);
                    }
                  }}
                  placeholder="Select parameter"
                  className="text-base-content"
                  styles={{
                    control: (base) => ({
                      ...base,
                      minHeight: '40px',
                      height: '40px',
                      borderRadius: '0.5rem'
                    }),
                    valueContainer: (base) => ({
                      ...base,
                      height: '40px',
                      padding: '0 8px'
                    }),
                    input: (base) => ({
                      ...base,
                      margin: '0px',
                      padding: '0px'
                    }),
                    indicatorsContainer: (base) => ({
                      ...base,
                      height: '40px'
                    }),
                  }}
                />
              </div>
            </div>

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

          {/* Statistics Display */}
          {median !== null && mean !== null && taskResponse?.data?.result && (
            <div className="stats shadow mt-4 grid-cols-2 lg:grid-cols-4 xl:grid-cols-5">
              <div className="stat">
                <div className="stat-title">N_total</div>
                <div className="stat-value text-info text-sm">
                  {Object.keys(taskResponse.data.result).length}
                </div>
                <div className="stat-desc">Total {taskType === 'coupling' ? 'pairs' : 'qubits'}</div>
              </div>
              <div className="stat">
                <div className="stat-title">N_valid</div>
                <div className="stat-value text-success text-sm">
                  {tableData.length}
                </div>
                <div className="stat-desc">With valid data</div>
              </div>
              <div className="stat">
                <div className="stat-title">N_disabled</div>
                <div className="stat-value text-warning text-sm">
                  {Object.keys(taskResponse.data.result).length - tableData.length}
                </div>
                <div className="stat-desc">Missing/invalid data</div>
              </div>
              <div className="stat">
                <div className="stat-title">Median</div>
                <div className="stat-value text-primary text-sm">
                  {median.toFixed(4)}
                </div>
              </div>
              <div className="stat">
                <div className="stat-title">Mean</div>
                <div className="stat-value text-secondary text-sm">
                  {mean.toFixed(4)}
                </div>
              </div>
              <div className="stat">
                <div className="stat-title">10th %ile</div>
                <div className="stat-value text-accent text-sm">
                  {percentile10?.toFixed(4)}
                </div>
              </div>
              <div className="stat">
                <div className="stat-title">90th %ile</div>
                <div className="stat-value text-accent text-sm">
                  {percentile90?.toFixed(4)}
                </div>
              </div>
              {avgR2 !== null && (
                <div className="stat">
                  <div className="stat-title">Avg R²</div>
                  <div className="stat-value text-info text-sm">
                    {avgR2.toFixed(3)}
                  </div>
                  <div className="stat-desc">Fit quality</div>
                </div>
              )}
              {avgError !== null && (
                <div className="stat">
                  <div className="stat-title">Avg Error</div>
                  <div className="stat-value text-warning text-sm">
                    {avgError.toFixed(6)}
                  </div>
                  <div className="stat-desc">Uncertainty</div>
                </div>
              )}
              {yieldPercent !== null && (
                <div className="stat">
                  <div className="stat-title">Yield</div>
                  <div className="stat-value text-success text-sm">
                    {yieldPercent.toFixed(1)}%
                  </div>
                  <div className="stat-desc">Above threshold</div>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {/* Plot Section */}
      <PlotCard
        plotData={plotData}
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
              { key: 'qid', label: 'Qubit ID', sortable: true },
              { 
                key: 'value', 
                label: 'Value', 
                sortable: true, 
                render: (v: number, row: CumulativeDataPoint) => {
                  const errorStr = row.error !== undefined ? ` ± ${row.error.toFixed(6)}` : '';
                  return `${v.toFixed(6)}${errorStr}`;
                }
              },
              { key: 'cdf', label: 'CDF', sortable: true, render: (v: number) => (v * 100).toFixed(2) + '%' },
              { key: 'survivalFunction', label: 'Survival', sortable: true, render: (v: number) => (v * 100).toFixed(2) + '%' },
              { 
                key: 'r2', 
                label: 'R²', 
                sortable: true, 
                render: (v: number | undefined) => v !== undefined ? v.toFixed(3) : 'N/A'
              },
            ]}
            pageSize={10}
          />
        </div>
      </div>
    </div>
  );
}