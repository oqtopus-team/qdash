import { useCallback, useState, useEffect } from "react";

import {
  useQueryState,
  parseAsString,
  parseAsArrayOf,
  parseAsBoolean,
  parseAsFloat,
  parseAsInteger,
} from "nuqs";

// Default values for URL parameters - used to determine when to remove params from URL
const URL_DEFAULTS = {
  DATE: "latest",
  TASK: "CheckRabi",
  VIEW: "1q",
  CDF_PARAMETERS: ["t1", "t2_echo", "t2_star"],
  SHOW_ERROR_RATE: false,
} as const;

interface UseChipUrlStateResult {
  selectedChip: string;
  selectedDate: string;
  selectedTask: string;
  viewMode: string;
  qubitViewMode: string;
  setSelectedChip: (chip: string) => void;
  setSelectedDate: (date: string) => void;
  setSelectedTask: (task: string) => void;
  setViewMode: (mode: string) => void;
  setQubitViewMode: (mode: string) => void;
  isInitialized: boolean; // Track if URL state has been initialized
}

interface UseExecutionUrlStateResult {
  selectedChip: string | null;
  setSelectedChip: (chip: string | null) => void;
  isInitialized: boolean;
}

interface UseAnalysisUrlStateResult {
  selectedChip: string;
  selectedParameter: string;
  selectedParameters: string[];
  selectedTag: string;
  analysisViewType: string;
  setSelectedChip: (chip: string) => void;
  setSelectedParameter: (parameter: string) => void;
  setSelectedParameters: (parameters: string[]) => void;
  setSelectedTag: (tag: string) => void;
  setAnalysisViewType: (type: string) => void;
  isInitialized: boolean;
}

interface UseQubitTimeSeriesUrlStateResult {
  selectedParameter: string;
  selectedTag: string;
  setSelectedParameter: (parameter: string) => void;
  setSelectedTag: (tag: string) => void;
  isInitialized: boolean;
}

interface UseCDFUrlStateResult {
  selectedChip: string;
  timeRange: TimeRange;
  selectionMode: SelectionMode;
  selectedParameters: string[];
  showAsErrorRate: boolean;
  setSelectedChip: (chip: string) => void;
  setTimeRange: (range: TimeRange) => void;
  setSelectionMode: (mode: SelectionMode) => void;
  setSelectedParameters: (parameters: string[]) => void;
  setShowAsErrorRate: (show: boolean) => void;
  isInitialized: boolean;
}

type TimeRange = "1d" | "7d" | "30d" | "custom";
type SelectionMode = "latest" | "best" | "average";

interface UseHistogramUrlStateResult {
  selectedChip: string;
  timeRange: TimeRange;
  selectionMode: SelectionMode;
  selectedParameter: string;
  showAsErrorRate: boolean;
  customThreshold: number | null;
  setSelectedChip: (chip: string) => void;
  setTimeRange: (range: TimeRange) => void;
  setSelectionMode: (mode: SelectionMode) => void;
  setSelectedParameter: (parameter: string) => void;
  setShowAsErrorRate: (show: boolean) => void;
  setCustomThreshold: (threshold: number | null) => void;
  isInitialized: boolean;
}

export function useChipUrlState(): UseChipUrlStateResult {
  const [isInitialized, setIsInitialized] = useState(false);

  // URL state management - don't use withDefault to preserve URL params
  const [selectedChip, setSelectedChipState] = useQueryState(
    "chip",
    parseAsString,
  );

  const [selectedDate, setSelectedDateState] = useQueryState(
    "date",
    parseAsString,
  );

  const [selectedTask, setSelectedTaskState] = useQueryState(
    "task",
    parseAsString,
  );

  const [viewMode, setViewModeState] = useQueryState("view", parseAsString);

  const [qubitViewMode, setQubitViewModeState] = useQueryState(
    "qview",
    parseAsString,
  );

  // Mark as initialized after first render
  useEffect(() => {
    setIsInitialized(true);
  }, []);

  // Wrapped setters to handle URL updates smoothly
  const setSelectedChip = useCallback(
    (chip: string) => {
      setSelectedChipState(chip || null); // null removes the parameter from URL
    },
    [setSelectedChipState],
  );

  const setSelectedDate = useCallback(
    (date: string) => {
      setSelectedDateState(date === URL_DEFAULTS.DATE ? null : date); // Remove default from URL
    },
    [setSelectedDateState],
  );

  const setSelectedTask = useCallback(
    (task: string) => {
      setSelectedTaskState(task === URL_DEFAULTS.TASK ? null : task); // Remove default from URL
    },
    [setSelectedTaskState],
  );

  const setViewMode = useCallback(
    (mode: string) => {
      setViewModeState(mode === URL_DEFAULTS.VIEW ? null : mode); // Remove default from URL
    },
    [setViewModeState],
  );

  const setQubitViewMode = useCallback(
    (mode: string) => {
      // Remove default qubit view mode from URL (e.g., if "dashboard" is default)
      setQubitViewModeState(mode === "dashboard" ? null : mode);
    },
    [setQubitViewModeState],
  );

  return {
    selectedChip: selectedChip ?? "",
    selectedDate: selectedDate ?? URL_DEFAULTS.DATE,
    selectedTask: selectedTask ?? URL_DEFAULTS.TASK,
    viewMode: viewMode ?? URL_DEFAULTS.VIEW,
    qubitViewMode: qubitViewMode ?? "dashboard",
    setSelectedChip,
    setSelectedDate,
    setSelectedTask,
    setViewMode,
    setQubitViewMode,
    isInitialized,
  };
}

export function useExecutionUrlState(): UseExecutionUrlStateResult {
  const [isInitialized, setIsInitialized] = useState(false);

  // URL state management for execution page
  const [selectedChip, setSelectedChipState] = useQueryState(
    "chip",
    parseAsString,
  );

  // Mark as initialized after first render
  useEffect(() => {
    setIsInitialized(true);
  }, []);

  // Wrapped setter to handle URL updates - now accepts null explicitly
  const setSelectedChip = useCallback(
    (chip: string | null) => {
      setSelectedChipState(chip || null); // null removes the parameter from URL
    },
    [setSelectedChipState],
  );

  return {
    selectedChip, // Return null as-is instead of converting to empty string
    setSelectedChip,
    isInitialized,
  };
}

export function useAnalysisUrlState(): UseAnalysisUrlStateResult {
  const [isInitialized, setIsInitialized] = useState(false);

  // URL state management for analysis pages
  const [selectedChip, setSelectedChipState] = useQueryState(
    "chip",
    parseAsString,
  );

  const [selectedParameter, setSelectedParameterState] = useQueryState(
    "parameter",
    parseAsString,
  );

  // Multiple parameters for dual-axis timeseries
  const [selectedParameters, setSelectedParametersState] = useQueryState(
    "params",
    parseAsArrayOf(parseAsString),
  );

  const [selectedTag, setSelectedTagState] = useQueryState(
    "tag",
    parseAsString,
  );

  const [analysisViewType, setAnalysisViewTypeState] = useQueryState(
    "aview",
    parseAsString,
  );

  // Mark as initialized after first render
  useEffect(() => {
    setIsInitialized(true);
  }, []);

  // Wrapped setters to handle URL updates
  const setSelectedChip = useCallback(
    (chip: string) => {
      setSelectedChipState(chip || null); // null removes the parameter from URL
    },
    [setSelectedChipState],
  );

  const setSelectedParameter = useCallback(
    (parameter: string) => {
      // Always include parameter in URL for complete state management
      setSelectedParameterState(parameter);
    },
    [setSelectedParameterState],
  );

  const setSelectedParameters = useCallback(
    (parameters: string[]) => {
      // Store multiple parameters for dual-axis view
      if (parameters.length === 0) {
        setSelectedParametersState(null);
      } else {
        setSelectedParametersState(parameters);
      }
    },
    [setSelectedParametersState],
  );

  const setSelectedTag = useCallback(
    (tag: string) => {
      // Always include tag in URL for complete state management
      setSelectedTagState(tag);
    },
    [setSelectedTagState],
  );

  const setAnalysisViewType = useCallback(
    (type: string) => {
      // Always include view type in URL for complete state management
      setAnalysisViewTypeState(type);
    },
    [setAnalysisViewTypeState],
  );

  return {
    selectedChip: selectedChip ?? "",
    selectedParameter: selectedParameter ?? "t1",
    selectedParameters: selectedParameters ?? [],
    selectedTag: selectedTag ?? "daily",
    analysisViewType: analysisViewType ?? "timeseries",
    setSelectedChip,
    setSelectedParameter,
    setSelectedParameters,
    setSelectedTag,
    setAnalysisViewType,
    isInitialized,
  };
}

interface UseCorrelationUrlStateResultNew {
  selectedChip: string;
  timeRange: TimeRange;
  selectionMode: SelectionMode;
  xParameter: string;
  yParameter: string;
  setSelectedChip: (chip: string) => void;
  setTimeRange: (range: TimeRange) => void;
  setSelectionMode: (mode: SelectionMode) => void;
  setXParameter: (parameter: string) => void;
  setYParameter: (parameter: string) => void;
  isInitialized: boolean;
}

export function useCorrelationUrlState(): UseCorrelationUrlStateResultNew {
  const [isInitialized, setIsInitialized] = useState(false);

  // URL state management for correlation view
  const [selectedChip, setSelectedChipState] = useQueryState(
    "chip",
    parseAsString,
  );

  const [timeRange, setTimeRangeState] = useQueryState("range", parseAsString);

  const [selectionMode, setSelectionModeState] = useQueryState(
    "mode",
    parseAsString,
  );

  const [xParameter, setXParameterState] = useQueryState(
    "xParam",
    parseAsString,
  );

  const [yParameter, setYParameterState] = useQueryState(
    "yParam",
    parseAsString,
  );

  // Mark as initialized after first render
  useEffect(() => {
    setIsInitialized(true);
  }, []);

  // Wrapped setters to handle URL updates
  const setSelectedChip = useCallback(
    (chip: string) => {
      setSelectedChipState(chip || null); // null removes the parameter from URL
    },
    [setSelectedChipState],
  );

  const setTimeRange = useCallback(
    (range: TimeRange) => {
      setTimeRangeState(range === "7d" ? null : range); // 7d as default
    },
    [setTimeRangeState],
  );

  const setSelectionMode = useCallback(
    (mode: SelectionMode) => {
      setSelectionModeState(mode === "latest" ? null : mode); // latest as default
    },
    [setSelectionModeState],
  );

  const setXParameter = useCallback(
    (parameter: string) => {
      setXParameterState(parameter === "t1" ? null : parameter); // t1 as default
    },
    [setXParameterState],
  );

  const setYParameter = useCallback(
    (parameter: string) => {
      setYParameterState(parameter === "t2_echo" ? null : parameter); // t2_echo as default
    },
    [setYParameterState],
  );

  return {
    selectedChip: selectedChip ?? "",
    timeRange: (timeRange as TimeRange) ?? "7d",
    selectionMode: (selectionMode as SelectionMode) ?? "latest",
    xParameter: xParameter ?? "t1",
    yParameter: yParameter ?? "t2_echo",
    setSelectedChip,
    setTimeRange,
    setSelectionMode,
    setXParameter,
    setYParameter,
    isInitialized,
  };
}

export function useQubitTimeSeriesUrlState(): UseQubitTimeSeriesUrlStateResult {
  const [isInitialized, setIsInitialized] = useState(false);

  // URL state management for qubit time series view
  const [selectedParameter, setSelectedParameterState] = useQueryState(
    "param",
    parseAsString,
  );

  const [selectedTag, setSelectedTagState] = useQueryState(
    "tag",
    parseAsString,
  );

  // Mark as initialized after first render
  useEffect(() => {
    setIsInitialized(true);
  }, []);

  // Wrapped setters to handle URL updates
  const setSelectedParameter = useCallback(
    (parameter: string) => {
      // Remove default parameter from URL (e.g., if "t1" is default)
      setSelectedParameterState(parameter === "t1" ? null : parameter);
    },
    [setSelectedParameterState],
  );

  const setSelectedTag = useCallback(
    (tag: string) => {
      // Remove default tag from URL (e.g., if "daily" is default)
      setSelectedTagState(tag === "daily" ? null : tag);
    },
    [setSelectedTagState],
  );

  return {
    selectedParameter: selectedParameter ?? "t1",
    selectedTag: selectedTag ?? "daily",
    setSelectedParameter,
    setSelectedTag,
    isInitialized,
  };
}

export function useCDFUrlState(): UseCDFUrlStateResult {
  const [isInitialized, setIsInitialized] = useState(false);

  // URL state management for CDF view
  const [selectedChip, setSelectedChipState] = useQueryState(
    "chip",
    parseAsString,
  );

  const [timeRange, setTimeRangeState] = useQueryState("range", parseAsString);

  const [selectionMode, setSelectionModeState] = useQueryState(
    "mode",
    parseAsString,
  );

  const [selectedParameters, setSelectedParametersState] = useQueryState(
    "params",
    parseAsArrayOf(parseAsString),
  );

  const [showAsErrorRate, setShowAsErrorRateState] = useQueryState(
    "errorRate",
    parseAsBoolean,
  );

  // Mark as initialized after first render
  useEffect(() => {
    setIsInitialized(true);
  }, []);

  // Helper function to check if arrays are equal
  const arraysEqual = (a: string[], b: string[]) => {
    if (a.length !== b.length) return false;
    return a.every((val, i) => val === b[i]);
  };

  // Wrapped setters to handle URL updates
  const setSelectedChip = useCallback(
    (chip: string) => {
      setSelectedChipState(chip || null); // null removes the parameter from URL
    },
    [setSelectedChipState],
  );

  const setTimeRange = useCallback(
    (range: TimeRange) => {
      setTimeRangeState(range === "7d" ? null : range); // 7d as default
    },
    [setTimeRangeState],
  );

  const setSelectionMode = useCallback(
    (mode: SelectionMode) => {
      setSelectionModeState(mode === "latest" ? null : mode); // latest as default
    },
    [setSelectionModeState],
  );

  const setSelectedParameters = useCallback(
    (parameters: string[]) => {
      // Remove default parameters from URL to keep it clean
      if (arraysEqual(parameters, [...URL_DEFAULTS.CDF_PARAMETERS])) {
        setSelectedParametersState(null);
      } else {
        setSelectedParametersState(parameters);
      }
    },
    [setSelectedParametersState],
  );

  const setShowAsErrorRate = useCallback(
    (show: boolean) => {
      setShowAsErrorRateState(
        show === URL_DEFAULTS.SHOW_ERROR_RATE ? null : show,
      ); // Remove default from URL
    },
    [setShowAsErrorRateState],
  );

  return {
    selectedChip: selectedChip ?? "",
    timeRange: (timeRange as TimeRange) ?? "7d",
    selectionMode: (selectionMode as SelectionMode) ?? "latest",
    selectedParameters: selectedParameters ?? [...URL_DEFAULTS.CDF_PARAMETERS],
    showAsErrorRate: showAsErrorRate ?? URL_DEFAULTS.SHOW_ERROR_RATE,
    setSelectedChip,
    setTimeRange,
    setSelectionMode,
    setSelectedParameters,
    setShowAsErrorRate,
    isInitialized,
  };
}

export function useHistogramUrlState(): UseHistogramUrlStateResult {
  const [isInitialized, setIsInitialized] = useState(false);

  // URL state management
  const [selectedChip, setSelectedChipState] = useQueryState(
    "chip",
    parseAsString,
  );

  const [timeRange, setTimeRangeState] = useQueryState("range", parseAsString);

  const [selectionMode, setSelectionModeState] = useQueryState(
    "mode",
    parseAsString,
  );

  const [selectedParameter, setSelectedParameterState] = useQueryState(
    "param",
    parseAsString,
  );

  const [showAsErrorRate, setShowAsErrorRateState] = useQueryState(
    "errorRate",
    parseAsBoolean,
  );

  const [customThreshold, setCustomThresholdState] = useQueryState(
    "threshold",
    parseAsFloat,
  );

  // Initialize state on mount
  useEffect(() => {
    setIsInitialized(true);
  }, []);

  const setSelectedChip = useCallback(
    (chip: string) => {
      setSelectedChipState(chip || null);
    },
    [setSelectedChipState],
  );

  const setTimeRange = useCallback(
    (range: TimeRange) => {
      setTimeRangeState(range === "7d" ? null : range); // 7d as default
    },
    [setTimeRangeState],
  );

  const setSelectionMode = useCallback(
    (mode: SelectionMode) => {
      setSelectionModeState(mode === "latest" ? null : mode); // latest as default
    },
    [setSelectionModeState],
  );

  const setSelectedParameter = useCallback(
    (parameter: string) => {
      setSelectedParameterState(parameter === "t1" ? null : parameter); // t1 as default
      // Clear custom threshold when parameter changes
      setCustomThresholdState(null);
    },
    [setSelectedParameterState, setCustomThresholdState],
  );

  const setShowAsErrorRate = useCallback(
    (show: boolean) => {
      setShowAsErrorRateState(
        show === URL_DEFAULTS.SHOW_ERROR_RATE ? null : show,
      );
    },
    [setShowAsErrorRateState],
  );

  const setCustomThreshold = useCallback(
    (threshold: number | null) => {
      setCustomThresholdState(threshold);
    },
    [setCustomThresholdState],
  );

  return {
    selectedChip: selectedChip ?? "",
    timeRange: (timeRange as TimeRange) ?? "7d",
    selectionMode: (selectionMode as SelectionMode) ?? "latest",
    selectedParameter: selectedParameter ?? "t1",
    showAsErrorRate: showAsErrorRate ?? URL_DEFAULTS.SHOW_ERROR_RATE,
    customThreshold: customThreshold ?? null,
    setSelectedChip,
    setTimeRange,
    setSelectionMode,
    setSelectedParameter,
    setShowAsErrorRate,
    setCustomThreshold,
    isInitialized,
  };
}

// Metrics page URL state
type MetricType = "qubit" | "coupling";

interface UseMetricsUrlStateResult {
  selectedChip: string;
  timeRange: TimeRange;
  selectionMode: SelectionMode;
  metricType: MetricType;
  selectedMetric: string;
  customDays: number | null;
  setSelectedChip: (chip: string) => void;
  setTimeRange: (range: TimeRange) => void;
  setSelectionMode: (mode: SelectionMode) => void;
  setMetricType: (type: MetricType) => void;
  setSelectedMetric: (metric: string) => void;
  setCustomDays: (days: number) => void;
  isInitialized: boolean;
}

export function useMetricsUrlState(): UseMetricsUrlStateResult {
  const [isInitialized, setIsInitialized] = useState(false);

  const [selectedChip, setSelectedChipState] = useQueryState(
    "chip",
    parseAsString,
  );

  const [timeRange, setTimeRangeState] = useQueryState("range", parseAsString);

  const [selectionMode, setSelectionModeState] = useQueryState(
    "mode",
    parseAsString,
  );

  const [metricType, setMetricTypeState] = useQueryState("type", parseAsString);

  const [selectedMetric, setSelectedMetricState] = useQueryState(
    "metric",
    parseAsString,
  );

  const [customDays, setCustomDaysState] = useQueryState(
    "days",
    parseAsInteger,
  );

  // Mark as initialized after first render
  useEffect(() => {
    setIsInitialized(true);
  }, []);

  const setSelectedChip = useCallback(
    (chip: string) => {
      setSelectedChipState(chip || null);
    },
    [setSelectedChipState],
  );

  const setTimeRange = useCallback(
    (range: TimeRange) => {
      setTimeRangeState(range === "7d" ? null : range);
      // Clear days param when switching away from custom
      if (range !== "custom") {
        setCustomDaysState(null);
      } else if (!customDays) {
        // Set default of 90 days when entering custom mode
        setCustomDaysState(90);
      }
    },
    [setTimeRangeState, setCustomDaysState, customDays],
  );

  const setSelectionMode = useCallback(
    (mode: SelectionMode) => {
      setSelectionModeState(mode === "latest" ? null : mode);
    },
    [setSelectionModeState],
  );

  const setMetricType = useCallback(
    (type: MetricType) => {
      setMetricTypeState(type === "qubit" ? null : type);
    },
    [setMetricTypeState],
  );

  const setSelectedMetric = useCallback(
    (metric: string) => {
      setSelectedMetricState(metric === "t1" ? null : metric);
    },
    [setSelectedMetricState],
  );

  const setCustomDays = useCallback(
    (days: number) => {
      setCustomDaysState(days);
    },
    [setCustomDaysState],
  );

  return {
    selectedChip: selectedChip ?? "",
    timeRange: (timeRange as TimeRange) ?? "7d",
    selectionMode: (selectionMode as SelectionMode) ?? "latest",
    metricType: (metricType as MetricType) ?? "qubit",
    selectedMetric: selectedMetric ?? "t1",
    customDays: customDays ?? null,
    setSelectedChip,
    setTimeRange,
    setSelectionMode,
    setMetricType,
    setSelectedMetric,
    setCustomDays,
    isInitialized,
  };
}

// Provenance page URL state
type ProvenanceTab = "history" | "lineage" | "compare" | "seeds";

interface UseProvenanceUrlStateResult {
  activeTab: ProvenanceTab;
  parameter: string;
  qid: string;
  entityId: string;
  setActiveTab: (tab: ProvenanceTab) => void;
  setParameter: (parameter: string) => void;
  setQid: (qid: string) => void;
  setEntityId: (entityId: string) => void;
  isInitialized: boolean;
  hasSearchParams: boolean;
}

export function useProvenanceUrlState(): UseProvenanceUrlStateResult {
  const [isInitialized, setIsInitialized] = useState(false);

  // URL state management for provenance page
  const [activeTab, setActiveTabState] = useQueryState("tab", parseAsString);
  const [parameter, setParameterState] = useQueryState(
    "parameter",
    parseAsString,
  );
  const [qid, setQidState] = useQueryState("qid", parseAsString);
  const [entityId, setEntityIdState] = useQueryState("entity", parseAsString);

  // Mark as initialized after first render
  useEffect(() => {
    setIsInitialized(true);
  }, []);

  // Wrapped setters
  const setActiveTab = useCallback(
    (tab: ProvenanceTab) => {
      setActiveTabState(tab === "history" ? null : tab); // history is default
    },
    [setActiveTabState],
  );

  const setParameter = useCallback(
    (param: string) => {
      setParameterState(param || null);
    },
    [setParameterState],
  );

  const setQid = useCallback(
    (q: string) => {
      setQidState(q || null);
    },
    [setQidState],
  );

  const setEntityId = useCallback(
    (id: string) => {
      setEntityIdState(id || null);
    },
    [setEntityIdState],
  );

  // Check if we have search params for automatic search
  const hasSearchParams = !!(parameter && qid);

  return {
    activeTab: (activeTab as ProvenanceTab) ?? "history",
    parameter: parameter ?? "",
    qid: qid ?? "",
    entityId: entityId ?? "",
    setActiveTab,
    setParameter,
    setQid,
    setEntityId,
    isInitialized,
    hasSearchParams,
  };
}
