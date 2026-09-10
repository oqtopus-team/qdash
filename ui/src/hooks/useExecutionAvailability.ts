"use client";

import { useQuery } from "@tanstack/react-query";

import type { ExecutionAvailabilityRequest } from "@/schemas";

import { checkExecutionAvailability } from "@/client/execution/execution";
import { useProject } from "@/contexts/ProjectContext";

export function useExecutionAvailability(request: ExecutionAvailabilityRequest, enabled = true) {
  const { projectId } = useProject();
  const query = useQuery({
    queryKey: ["execution-availability", projectId, request],
    queryFn: ({ signal }) => checkExecutionAvailability(request, { signal }),
    enabled: enabled && Boolean(projectId),
    refetchInterval: 2000,
    refetchOnWindowFocus: "always",
    staleTime: 0,
    retry: false,
  });

  let disabledReason: string | null = null;
  let isConflict = false;
  if (query.fetchStatus === "paused") {
    disabledReason = "Unable to check hardware availability while offline.";
  } else if (query.isError) {
    disabledReason = "Unable to check hardware availability. Retrying automatically…";
  } else if (!query.data || !query.isFetchedAfterMount) {
    disabledReason = "Checking hardware availability…";
  } else if (!query.data.data.available) {
    isConflict = true;
    disabledReason = query.data.data.reason || "Hardware required by this run is in use.";
  }

  return { disabledReason, isConflict, refetch: query.refetch };
}
