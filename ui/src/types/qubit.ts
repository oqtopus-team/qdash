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

export type TagKey = "latest" | "daily" | "weekly" | "monthly";

export interface TimeSeriesDataPoint {
  time: string;
  value: number | string;
  error?: number;
  unit: string;
}

export interface TimeRangeState {
  startAt: string;
  endAt: string;
  isStartAtLocked: boolean;
  isEndAtLocked: boolean;
}
