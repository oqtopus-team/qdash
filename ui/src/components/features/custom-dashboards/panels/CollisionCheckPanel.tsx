"use client";

import { useMemo, useState } from "react";

import { useQuery } from "@tanstack/react-query";

import {
  evaluateCollisionCheck,
  useListCollisionChecks,
} from "@/client/collision-analysis/collision-analysis";
import type { CollisionCellResponse, CollisionCheckInfo } from "@/schemas";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import { formatDateTime } from "@/lib/utils/datetime";

import { type CollisionPanelConfig, formatNumber } from "../panelConfig";
import { CollisionCellDialog } from "./CollisionCellDialog";
import { CollisionMap } from "./CollisionMap";
import { PanelMessage, PanelSkeleton } from "./PanelStates";

/** Query key of one evaluation; params and hops are part of it so edits refetch. */
function collisionQueryKey(chipId: string, config: CollisionPanelConfig) {
  return ["collision-analysis", chipId, config.check, config.params, config.hops] as const;
}

/** "CNOT time 500 ns · max detuning 1.5 GHz" from the effective parameters. */
function formatCollisionParameters(
  parameters: Record<string, number>,
  info: CollisionCheckInfo | undefined,
): string {
  return Object.entries(parameters)
    .map(([name, value]) => {
      const spec = info?.parameters.find((parameter) => parameter.name === name);
      const label = (spec?.label || name).replace(/_/g, " ");
      return [label, formatNumber(value), spec?.unit].filter(Boolean).join(" ");
    })
    .join(" · ");
}

interface CollisionCheckPanelProps {
  chipId: string;
  topologyId: string;
  config: CollisionPanelConfig;
}

export function CollisionCheckPanel({ chipId, topologyId, config }: CollisionCheckPanelProps) {
  const [selectedCell, setSelectedCell] = useState<CollisionCellResponse | null>(null);
  const { data: catalog } = useListCollisionChecks({ query: { staleTime: Infinity } });
  const info = catalog?.data.checks.find((check) => check.kind === config.check);

  const { data, isLoading, isError, error, isFetching } = useQuery({
    queryKey: collisionQueryKey(chipId, config),
    queryFn: ({ signal }) =>
      evaluateCollisionCheck(
        chipId,
        // Qubit checks ignore hops; the stored value is always a valid subset.
        { check: config.check, params: config.params, hops: config.hops },
        undefined,
        signal,
      ),
    enabled: !!chipId && !!config.check,
    staleTime: 30_000,
  });
  const response = data?.data;

  const parameterText = useMemo(
    () => (response ? formatCollisionParameters(response.parameters, info) : ""),
    [info, response],
  );

  if (!config.check) {
    return <PanelMessage tone="warning">Choose a collision check for this panel</PanelMessage>;
  }
  if (!chipId) return <PanelMessage>Select a chip to show this panel</PanelMessage>;
  if (isLoading) return <PanelSkeleton />;
  if (isError || !response) {
    return (
      <PanelMessage tone="error">
        {getApiErrorMessage(error, "Failed to evaluate the collision check")}
      </PanelMessage>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col gap-2" aria-busy={isFetching}>
      <p className="truncate text-xs text-base-content/60" title={response.description}>
        {response.title}
        {response.unit !== "dimensionless" ? ` · ${response.unit}` : ""}
      </p>
      <div className="min-h-0 flex-1">
        <CollisionMap response={response} topologyId={topologyId} onSelectCell={setSelectedCell} />
      </div>
      <div className="flex items-center justify-between gap-2 border-t border-base-content/10 pt-1.5 text-xs text-base-content/60">
        {parameterText ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <span className="min-w-0 truncate" tabIndex={0}>
                {parameterText}
              </span>
            </TooltipTrigger>
            <TooltipContent className="max-w-md">{parameterText}</TooltipContent>
          </Tooltip>
        ) : (
          <span />
        )}
        <span className="shrink-0">Evaluated {formatDateTime(response.evaluated_at)}</span>
      </div>
      <CollisionCellDialog
        cell={selectedCell}
        checkTitle={response.title}
        onOpenChange={(open) => !open && setSelectedCell(null)}
      />
    </div>
  );
}
