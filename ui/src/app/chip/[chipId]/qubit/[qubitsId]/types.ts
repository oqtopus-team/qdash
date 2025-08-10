// Type definitions for qubit analysis components

export type ParameterKey = 
  | "t1" 
  | "t2_echo" 
  | "t2_star"
  | "frequency"
  | "anharmonicity"
  | "fidelity"
  | "readout_fidelity"
  | "gate_fidelity"
  | "drag_coefficient"
  | "pi_pulse_amplitude"
  | "pi_pulse_duration";

export type TagKey = 
  | "latest"
  | "daily" 
  | "weekly"
  | "monthly";

export type SortDirection = "asc" | "desc";

export type ViewMode = "dashboard" | "timeseries" | "correlation" | "comparison";

export interface TimeSeriesDataPoint {
  time: string;
  value: number | string;
  error?: number;
  unit: string;
}

export interface CorrelationDataPoint {
  time: string;
  x: number;
  y: number;
  xUnit: string;
  yUnit: string;
  xDescription: string;
  yDescription: string;
}

export interface StatisticalSummary {
  correlation: number;
  xMean: number;
  yMean: number;
  xStd: number;
  yStd: number;
  xMin: number;
  xMax: number;
  yMin: number;
  yMax: number;
  dataPoints: number;
}

export interface TimeRangeState {
  startAt: string;
  endAt: string;
  isStartAtLocked: boolean;
  isEndAtLocked: boolean;
}

export interface CSVExportData {
  headers: string[];
  rows: string[][];
  filename: string;
}