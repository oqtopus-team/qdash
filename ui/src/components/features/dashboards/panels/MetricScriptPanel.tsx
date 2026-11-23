"use client";

import { useState } from "react";

import { useQuery } from "@tanstack/react-query";
import { ArrowUpCircle, Info } from "lucide-react";

import {
  evaluateMetricScript,
  evaluateMetricScriptDraft,
} from "@/client/metric-script/metric-script";
import type { DashboardPanelResponse } from "@/schemas";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";
import { formatParams } from "@/components/features/metric-scripts/parameters";
import { formatPeriod } from "@/components/features/metric-scripts/periods";
import { MetricResultView } from "@/components/features/metric-scripts/render/MetricResultView";
import type { PairDirection } from "@/components/features/metric-scripts/render/PairMap";

import { metricScriptConfigError, readMetricScriptConfig } from "../panelConfig";
import { PanelMessage } from "./PanelStates";

interface MetricScriptPanelProps {
  panel: DashboardPanelResponse;
  chipId: string;
  topologyId: string;
  editing: boolean;
  /** Move the pinned revision to the script's active revision (edit mode only). */
  onUpdateRevision: () => void;
  /**
   * For a template preview whose script is not in the project yet: the starter script that
   * Save adds. Its source is evaluated as an unsaved draft; nothing is stored.
   */
  starterScript?: { name: string; source: string };
}

/**
 * A metric of a saved script, evaluated at the panel's pinned revision with its period and
 * parameters. An updated definition (newer active revision) is announced; only an editor's
 * explicit action moves the pin, and the revision numbers stay in the footer and tooltips.
 */
export function MetricScriptPanel({
  panel,
  chipId,
  topologyId,
  editing,
  onUpdateRevision,
  starterScript,
}: MetricScriptPanelProps) {
  const config = readMetricScriptConfig(panel);
  // A starter script has no ID or revision yet; the rest of the config still applies.
  const configError = starterScript
    ? metricScriptConfigError({ ...config, script_id: "starter", script_revision: 0 })
    : metricScriptConfigError(config);
  // Viewers may flip the direction for themselves; the stored default comes back on reload.
  const [direction, setDirection] = useState<PairDirection>(config.direction);
  const [storedDirection, setStoredDirection] = useState<PairDirection>(config.direction);
  if (storedDirection !== config.direction) {
    setStoredDirection(config.direction);
    setDirection(config.direction);
  }

  const query = useQuery({
    queryKey: [
      "metric-script-evaluate",
      starterScript ? { starter: starterScript.source } : config.script_id,
      config.script_revision,
      chipId,
      config.metric_id,
      config.period,
      config.params,
      config.targets,
    ] as const,
    queryFn: ({ signal }) => {
      // Only a series panel selects targets; the server evaluates nothing else.
      const body = {
        metric_id: config.metric_id,
        chip_id: chipId,
        period: config.period,
        params: config.params,
        ...(config.targets.length > 0 ? { targets: config.targets } : {}),
      };
      return starterScript
        ? evaluateMetricScriptDraft({ ...body, source: starterScript.source }, undefined, signal)
        : evaluateMetricScript(
            config.script_id,
            { ...body, revision: config.script_revision },
            undefined,
            signal,
          );
    },
    enabled: !!chipId && configError === null,
    staleTime: 30_000,
    retry: false,
  });
  const result = query.data?.data;

  if (configError) return <PanelMessage tone="warning">{configError}</PanelMessage>;
  if (!chipId) return <PanelMessage>Select a chip to show this panel</PanelMessage>;

  const latest = panel.latest_revision ?? null;
  const pinned = config.script_revision ?? 0;
  const newer = latest !== null && latest > pinned;
  const scriptName = panel.script_name ?? config.script_id;
  const footerParts = [
    starterScript ? `${starterScript.name} (added on save)` : `${scriptName} r${pinned}`,
    result?.metric.title ?? config.metric_id,
    formatPeriod(config.period),
  ];
  const paramText = result ? formatParams(result.params, result.metric) : "";
  const footer = [...footerParts, paramText].filter(Boolean).join(" · ");

  return (
    <div className="flex h-full min-h-0 flex-col gap-2">
      {newer && (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <span
            className="inline-flex items-center gap-1 text-info"
            title={`Showing revision r${pinned}; the script's active revision is r${latest}`}
          >
            <Info className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            Update available
          </span>
          {editing && (
            <button
              type="button"
              className="btn btn-ghost btn-xs"
              title={`Switch this panel from r${pinned} to r${latest}`}
              onClick={onUpdateRevision}
            >
              <ArrowUpCircle data-icon="inline-start" aria-hidden="true" />
              Use updated definition
            </button>
          )}
        </div>
      )}
      <div className="min-h-0 flex-1">
        <MetricResultView
          result={result}
          error={query.error}
          isLoading={query.isLoading}
          isFetching={query.isFetching}
          topologyId={topologyId}
          view={config.view}
          direction={direction}
          onDirectionChange={setDirection}
          hops={config.hops}
          onRetry={() => void query.refetch()}
          compact
        />
      </div>
      <div className="flex items-center gap-2 border-t border-base-content/10 pt-1.5 text-xs text-base-content/60">
        <Tooltip>
          <TooltipTrigger asChild>
            <span className="min-w-0 truncate" tabIndex={0} data-testid="metric-script-footer">
              {footer}
            </span>
          </TooltipTrigger>
          <TooltipContent className="max-w-md">{footer}</TooltipContent>
        </Tooltip>
      </div>
    </div>
  );
}
