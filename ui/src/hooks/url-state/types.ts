// Default values for URL parameters - used to determine when to remove params from URL
export const URL_DEFAULTS = {
  DATE: "latest",
  TASK: "CheckRabi",
  VIEW: "1q",
  CDF_PARAMETERS: ["t1", "t2_echo", "t2_star"],
  SHOW_ERROR_RATE: false,
} as const;

export type TimeRange = "1d" | "7d" | "30d" | "custom";
export type SelectionMode = "latest" | "best" | "average";
export type MetricType = "qubit" | "coupling";
export type ProvenanceTab = "history" | "lineage" | "compare" | "seeds";
