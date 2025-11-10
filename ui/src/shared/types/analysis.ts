// Shared types for analysis components across qubit detail and analysis pages

export interface TimeSeriesDataPoint {
  time: string;
  value: number | string;
  error?: number;
  unit: string;
  qid?: string;
}

export interface CorrelationDataPoint {
  time: string;
  x: number;
  y: number;
  xUnit: string;
  yUnit: string;
  xDescription?: string;
  yDescription?: string;
  qid?: string;
}

export interface StatisticalSummary {
  correlation?: number;
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

export type ParameterKey =
  | "t1"
  | "t2_echo"
  | "t2_star"
  | "frequency"
  | "amplitude"
  | "phase"
  | "fidelity"
  | "gate_duration"
  | string; // Allow any string for backward compatibility

export type TagKey = "daily" | "weekly" | "monthly" | string; // Allow any string for backward compatibility

export interface CSVExportOptions {
  filename: string;
  headers: string[];
  data: (string | number)[][];
}
