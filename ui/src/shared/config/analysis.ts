// Shared configuration for analysis components

// Task names and types mapping
export const TASK_CONFIG: Record<
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
  bell_state_fidelity: { name: "CheckBellStateTomography", type: "coupling" },
  readout_fidelity: { name: "ReadoutClassification", type: "qubit" },
};

// Parameter configuration with QEC thresholds
export const PARAMETER_CONFIG: Record<
  string,
  {
    label: string;
    higherIsBetter: boolean;
    unit: string;
    displayUnit: string;
    threshold?: number;
  }
> = {
  t1: {
    label: "T1",
    higherIsBetter: true,
    unit: "µs",
    displayUnit: "µs",
    threshold: 100,
  },
  t2_echo: {
    label: "T2 Echo",
    higherIsBetter: true,
    unit: "µs",
    displayUnit: "µs",
    threshold: 200,
  },
  t2_star: {
    label: "T2*",
    higherIsBetter: true,
    unit: "µs",
    displayUnit: "µs",
    threshold: 50,
  },
  gate_fidelity: {
    label: "Average Gate Fidelity",
    higherIsBetter: true,
    unit: "percentage",
    displayUnit: "%",
    threshold: 0.99,
  },
  x90_fidelity: {
    label: "X90 Gate Fidelity",
    higherIsBetter: true,
    unit: "percentage",
    displayUnit: "%",
    threshold: 0.999,
  },
  x180_fidelity: {
    label: "X180 Gate Fidelity",
    higherIsBetter: true,
    unit: "percentage",
    displayUnit: "%",
    threshold: 0.999,
  },
  zx90_fidelity: {
    label: "ZX90 Gate Fidelity (2Q)",
    higherIsBetter: true,
    unit: "percentage",
    displayUnit: "%",
    threshold: 0.99,
  },
  bell_state_fidelity: {
    label: "Bell State Fidelity (2Q)",
    higherIsBetter: true,
    unit: "percentage",
    displayUnit: "%",
    threshold: 0.95,
  },
  readout_fidelity: {
    label: "Readout Fidelity",
    higherIsBetter: true,
    unit: "percentage",
    displayUnit: "%",
    threshold: 0.99,
  },
};

// Output parameter names for each task
export const OUTPUT_PARAM_NAMES: Record<string, string> = {
  t1: "t1",
  t2_echo: "t2_echo",
  t2_star: "t2_star",
  gate_fidelity: "average_gate_fidelity",
  x90_fidelity: "x90_gate_fidelity",
  x180_fidelity: "x180_gate_fidelity",
  zx90_fidelity: "zx90_gate_fidelity",
  bell_state_fidelity: "bell_state_fidelity",
  readout_fidelity: "average_readout_fidelity",
};

// Parameter groups for UI organization
export const PARAMETER_GROUPS = {
  coherence: ["t1", "t2_echo", "t2_star"] as const,
  fidelity: [
    "gate_fidelity",
    "x90_fidelity",
    "x180_fidelity",
    "zx90_fidelity",
    "bell_state_fidelity",
    "readout_fidelity",
  ] as const,
} as const;

// Threshold range configurations for sliders
export const THRESHOLD_RANGES: Record<
  string,
  { min: number; max: number; step: number }
> = {
  t1: { min: 25, max: 200, step: 1 },
  t2_echo: { min: 50, max: 400, step: 1 },
  t2_star: { min: 15, max: 100, step: 1 },
  // Fidelity parameters (as raw values, converted in UI)
  gate_fidelity: { min: 0.9, max: 0.999, step: 0.001 },
  x90_fidelity: { min: 0.9, max: 0.999, step: 0.001 },
  x180_fidelity: { min: 0.9, max: 0.999, step: 0.001 },
  zx90_fidelity: { min: 0.9, max: 0.999, step: 0.001 },
  bell_state_fidelity: { min: 0.8, max: 0.999, step: 0.001 },
  readout_fidelity: { min: 0.9, max: 0.999, step: 0.001 },
};

// Error rate ranges (for error rate display mode)
export const ERROR_RATE_RANGES: Record<
  string,
  { min: number; max: number; step: number }
> = {
  gate_fidelity: { min: 0.001, max: 0.1, step: 0.001 },
  x90_fidelity: { min: 0.001, max: 0.1, step: 0.001 },
  x180_fidelity: { min: 0.001, max: 0.1, step: 0.001 },
  zx90_fidelity: { min: 0.001, max: 0.1, step: 0.001 },
  bell_state_fidelity: { min: 0.001, max: 0.2, step: 0.001 },
  readout_fidelity: { min: 0.001, max: 0.1, step: 0.001 },
};

// Utility functions
export function isCoherenceParameter(parameter: string): boolean {
  return PARAMETER_GROUPS.coherence.includes(parameter as any);
}

export function isFidelityParameter(parameter: string): boolean {
  return PARAMETER_GROUPS.fidelity.includes(parameter as any);
}

export function getParameterRange(
  parameter: string,
  showAsErrorRate: boolean = false
) {
  if (isCoherenceParameter(parameter)) {
    return THRESHOLD_RANGES[parameter];
  }

  if (showAsErrorRate && ERROR_RATE_RANGES[parameter]) {
    return ERROR_RATE_RANGES[parameter];
  }

  return THRESHOLD_RANGES[parameter];
}

export function convertThresholdForDisplay(
  parameter: string,
  threshold: number,
  showAsErrorRate: boolean = false
): number {
  if (isCoherenceParameter(parameter)) {
    return threshold;
  }

  if (showAsErrorRate) {
    return 1 - threshold; // Convert fidelity to error rate
  }

  return threshold;
}

export function convertDisplayToThreshold(
  parameter: string,
  displayValue: number,
  showAsErrorRate: boolean = false
): number {
  if (isCoherenceParameter(parameter)) {
    return displayValue;
  }

  if (showAsErrorRate) {
    return 1 - displayValue; // Convert error rate back to fidelity
  }

  return displayValue;
}

export function formatThresholdValue(
  parameter: string,
  threshold: number,
  showAsErrorRate: boolean = false
): string {
  const config = PARAMETER_CONFIG[parameter];
  if (!config) return String(threshold);

  if (isCoherenceParameter(parameter)) {
    return `${threshold.toFixed(0)}${config.displayUnit}`;
  }

  if (showAsErrorRate) {
    const errorRate = (1 - threshold) * 100;
    return `${errorRate.toFixed(2)}%`;
  }

  const percentage = threshold * 100;
  return `${percentage.toFixed(2)}%`;
}
