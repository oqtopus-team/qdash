"use client";

import { useQuery } from "@tanstack/react-query";

import type { FlowExecutionPlanResponse } from "@/schemas";

import { getFlowExecutionPlan } from "@/client/flow/flow";
import { useProject } from "@/contexts/ProjectContext";
import { getApiErrorMessage } from "@/lib/utils/apiError";

export type FlowExecutionPlanState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "stale" }
  | { status: "ready"; plan: FlowExecutionPlanResponse };

interface FlowExecutionPlanRequest {
  flowName: string;
  chipId: string;
  /** `updated_at` of the saved flow the editor shows; part of the cache key. */
  sourceVersion: string | undefined;
  enabled: boolean;
}

/**
 * The execution preview of the saved flow source for one chip.
 *
 * Each project, flow, chip and saved version has its own query, so a response for an earlier
 * selection is never shown for the current one, and React Query aborts superseded requests.
 * A response read from another saved version than the editor knows is reported as stale.
 */
export function useFlowExecutionPlan({
  flowName,
  chipId,
  sourceVersion,
  enabled,
}: FlowExecutionPlanRequest): FlowExecutionPlanState {
  const { projectId } = useProject();
  const query = useQuery({
    queryKey: ["flow-execution-plan", projectId, flowName, chipId, sourceVersion],
    queryFn: ({ signal }) => getFlowExecutionPlan(flowName, { chip_id: chipId }, undefined, signal),
    enabled: enabled && Boolean(projectId && flowName && chipId),
    staleTime: 0,
    retry: false,
    refetchOnWindowFocus: false,
  });

  if (!chipId) return { status: "error", message: "Select a chip to preview this execution." };
  if (query.isError) {
    return {
      status: "error",
      message: getApiErrorMessage(query.error, "The execution preview could not be loaded."),
    };
  }
  const plan = query.data?.data;
  if (!plan || plan.chip_id !== chipId || plan.flow_name !== flowName) return { status: "loading" };
  if (sourceVersion && Date.parse(plan.source_updated_at) !== Date.parse(sourceVersion)) {
    return { status: "stale" };
  }
  return { status: "ready", plan };
}
