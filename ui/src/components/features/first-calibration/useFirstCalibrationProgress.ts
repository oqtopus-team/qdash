"use client";

import { useMemo } from "react";

import { isAxiosError } from "axios";

import { useListChipConfigSources, useListChips } from "@/client/chip/chip";
import { useGetExecution } from "@/client/execution/execution";
import { useGetFlow } from "@/client/flow/flow";
import { resolveChipSetupMode, type ChipSetupMode } from "@/components/features/chip/chipSetupMode";
import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";
import { isExecutionInProgress } from "@/lib/executionStatus";
import type { JourneyState } from "@/lib/firstCalibrationJourney";
import type { ChipResponse, ListConfigSourcesResponse } from "@/schemas";

import { journeyQueryKeys, type JourneyScope } from "./journeyQueryKeys";
import { deriveJourneyProgress, type JourneyProgress, type RecordLookup } from "./journeyProgress";

function lookup<T>(
  enabled: boolean,
  query: {
    isLoading: boolean;
    isError: boolean;
    error: unknown;
    data: T | undefined;
  },
): RecordLookup<T> {
  if (!enabled) return { status: "none" };
  if (query.data !== undefined) return { status: "ready", data: query.data };
  if (query.isError) {
    return isAxiosError(query.error) && query.error.response?.status === 404
      ? { status: "missing" }
      : { status: "error" };
  }
  return { status: "loading" };
}

/** The user and project the journey's records are read in, or null before both are known. */
export function useJourneyScope(): JourneyScope | null {
  const { username } = useAuth();
  const { projectId } = useProject();
  return useMemo(
    () => (username && projectId ? { username, projectId } : null),
    [username, projectId],
  );
}

/** The project's chips as the journey reads them: loading, failed, or the list. */
export type JourneyChipList =
  | { status: "loading" }
  | { status: "error" }
  | { status: "ready"; chips: readonly ChipResponse[] };

export interface FirstCalibrationProgressResult {
  progress: JourneyProgress | null;
  setup: ChipSetupMode;
  configSources: ListConfigSourcesResponse | undefined;
  /** Chips of the current project; only loaded for a journey or with `loadSetup`. */
  chipList: JourneyChipList;
  /** Fetch the deployment setup and the chip list again, e.g. after a failed load. */
  retrySetup: () => void;
}

/**
 * Server-backed progress of a stored journey. The chip, flow and execution the journey names are
 * read from the API, and the execution is polled while it runs.
 *
 * Every query key carries the user and project (see `journeyQueryKeys`), so after a project
 * switch the journey of the new project waits for that project's answers instead of reading the
 * cached records of the old one.
 */
export function useFirstCalibrationProgress(
  state: JourneyState | null,
  { loadSetup = false }: { loadSetup?: boolean } = {},
): FirstCalibrationProgressResult {
  const scope = useJourneyScope();
  const active = state !== null && scope !== null;
  const setupEnabled = scope !== null && (active || loadSetup);
  const chipsQuery = useListChips({
    query: {
      queryKey: journeyQueryKeys.chips(scope),
      enabled: setupEnabled,
      staleTime: 30_000,
    },
  });
  const configQuery = useListChipConfigSources({
    query: {
      queryKey: journeyQueryKeys.configSources(scope),
      enabled: setupEnabled,
      staleTime: 60_000,
    },
  });

  const flowName = state?.flowName ?? "";
  const flowEnabled = active && flowName !== "";
  const flowQuery = useGetFlow(flowName, {
    query: {
      queryKey: journeyQueryKeys.flow(scope, flowName),
      enabled: flowEnabled,
      retry: false,
    },
  });

  const executionId = state?.executionId ?? "";
  const executionEnabled = active && executionId !== "";
  const executionQuery = useGetExecution(executionId, {
    query: {
      queryKey: journeyQueryKeys.execution(scope, executionId),
      enabled: executionEnabled,
      retry: false,
      refetchInterval: (query) =>
        isExecutionInProgress(query.state.data?.data?.status) || !query.state.data ? 5000 : false,
    },
  });

  const configData = setupEnabled ? configQuery.data?.data : undefined;
  const configFailed = setupEnabled && configQuery.isError && configData === undefined;
  const setup = useMemo(
    () => resolveChipSetupMode(configData, { isError: configFailed }),
    [configData, configFailed],
  );

  const chips = setupEnabled ? chipsQuery.data?.data?.chips : undefined;
  const chipsFailed = setupEnabled && chipsQuery.isError && chips === undefined;
  const chipsFetching = chipsQuery.isFetching;
  const flowData = flowQuery.data?.data;
  const executionData = executionQuery.data?.data;

  const chipList = useMemo((): JourneyChipList => {
    if (chips) return { status: "ready", chips };
    return chipsFailed ? { status: "error" } : { status: "loading" };
  }, [chips, chipsFailed]);

  const progress = useMemo(() => {
    if (!state || !scope) return null;
    const knownChipIds = chips ? new Set(chips.map((chip) => chip.chip_id)) : null;
    // A chip created a moment ago is missing until the refetch its creation started lands.
    const chipIds =
      knownChipIds && state.chipId && !knownChipIds.has(state.chipId) && chipsFetching
        ? null
        : knownChipIds;
    return deriveJourneyProgress(state, {
      setup,
      chipIds,
      chipsFailed,
      flow: lookup(flowEnabled, {
        isLoading: flowQuery.isLoading,
        isError: flowQuery.isError,
        error: flowQuery.error,
        data: flowData ? { chipId: flowData.chip_id } : undefined,
      }),
      execution: lookup(executionEnabled, {
        isLoading: executionQuery.isLoading,
        isError: executionQuery.isError,
        error: executionQuery.error,
        data: executionData,
      }),
    });
  }, [
    state,
    scope,
    setup,
    chips,
    chipsFetching,
    chipsFailed,
    flowEnabled,
    flowQuery.isLoading,
    flowQuery.isError,
    flowQuery.error,
    flowData,
    executionEnabled,
    executionQuery.isLoading,
    executionQuery.isError,
    executionQuery.error,
    executionData,
  ]);

  const refetchConfig = configQuery.refetch;
  const refetchChips = chipsQuery.refetch;
  const retrySetup = useMemo(
    () => () => {
      void refetchConfig();
      void refetchChips();
    },
    [refetchConfig, refetchChips],
  );

  return { progress, setup, configSources: configData, chipList, retrySetup };
}
