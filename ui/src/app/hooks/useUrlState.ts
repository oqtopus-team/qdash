import { useQueryState, parseAsString } from "nuqs";
import { useCallback, useState, useEffect } from "react";

// Default values for URL parameters - used to determine when to remove params from URL
const URL_DEFAULTS = {
  DATE: "latest",
  TASK: "CheckRabi",
  VIEW: "1q",
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
  selectedTag: string;
  analysisViewType: string;
  setSelectedChip: (chip: string) => void;
  setSelectedParameter: (parameter: string) => void;
  setSelectedTag: (tag: string) => void;
  setAnalysisViewType: (type: string) => void;
  isInitialized: boolean;
}

interface UseCorrelationUrlStateResult {
  selectedChip: string;
  xAxis: string;
  yAxis: string;
  setSelectedChip: (chip: string) => void;
  setXAxis: (parameter: string) => void;
  setYAxis: (parameter: string) => void;
  isInitialized: boolean;
}

interface UseQubitTimeSeriesUrlStateResult {
  selectedParameter: string;
  selectedTag: string;
  setSelectedParameter: (parameter: string) => void;
  setSelectedTag: (tag: string) => void;
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

  const [qubitViewMode, setQubitViewModeState] = useQueryState("qview", parseAsString);

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
    selectedTag: selectedTag ?? "daily",
    analysisViewType: analysisViewType ?? "correlation",
    setSelectedChip,
    setSelectedParameter,
    setSelectedTag,
    setAnalysisViewType,
    isInitialized,
  };
}

export function useCorrelationUrlState(): UseCorrelationUrlStateResult {
  const [isInitialized, setIsInitialized] = useState(false);

  // URL state management for correlation view
  const [selectedChip, setSelectedChipState] = useQueryState(
    "chip",
    parseAsString,
  );

  const [xAxis, setXAxisState] = useQueryState(
    "xAxis",
    parseAsString,
  );

  const [yAxis, setYAxisState] = useQueryState(
    "yAxis", 
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

  const setXAxis = useCallback(
    (parameter: string) => {
      // Always include parameter in URL for complete state management
      setXAxisState(parameter);
    },
    [setXAxisState],
  );

  const setYAxis = useCallback(
    (parameter: string) => {
      // Always include parameter in URL for complete state management
      setYAxisState(parameter);
    },
    [setYAxisState],
  );

  return {
    selectedChip: selectedChip ?? "",
    xAxis: xAxis ?? "t1",
    yAxis: yAxis ?? "t2_echo",
    setSelectedChip,
    setXAxis,
    setYAxis,
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

