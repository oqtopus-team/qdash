"use client";

import type { CSSProperties } from "react";

import {
  ArrowDown,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  Copy,
  EllipsisVertical,
  FoldHorizontal,
  FoldVertical,
  Pencil,
  Trash2,
  UnfoldHorizontal,
  UnfoldVertical,
} from "lucide-react";

import type { DashboardPanelResponse } from "@/schemas";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";

import { canApplyLayoutAction, type LayoutAction, panelHeightPx } from "./layout";
import { panelTypeMeta, readMarkdownContent, readMetricConfig } from "./panelConfig";
import { MarkdownPanel } from "./panels/MarkdownPanel";
import { CouplingMetricPanel, QubitMetricPanel } from "./panels/MetricPanels";
import { MetricScriptPanel } from "./panels/MetricScriptPanel";

/** `update-revision` moves a metric script panel's pin to the script's active revision. */
export type PanelCommand = LayoutAction | "edit" | "duplicate" | "remove" | "update-revision";

const LAYOUT_ITEMS: ReadonlyArray<{
  action: LayoutAction;
  label: string;
  icon: typeof ArrowLeft;
}> = [
  { action: "left", label: "Move left", icon: ArrowLeft },
  { action: "right", label: "Move right", icon: ArrowRight },
  { action: "up", label: "Move up", icon: ArrowUp },
  { action: "down", label: "Move down", icon: ArrowDown },
  { action: "wider", label: "Wider", icon: UnfoldHorizontal },
  { action: "narrower", label: "Narrower", icon: FoldHorizontal },
  { action: "taller", label: "Taller", icon: UnfoldVertical },
  { action: "shorter", label: "Shorter", icon: FoldVertical },
];

function PanelBody({
  panel,
  chipId,
  topologyId,
  editing,
  onCommand,
}: {
  panel: DashboardPanelResponse;
  chipId: string;
  topologyId: string;
  editing: boolean;
  onCommand: (panelId: string, command: PanelCommand) => void;
}) {
  switch (panel.type) {
    case "qubit_metric": {
      const config = readMetricConfig(panel);
      return (
        <QubitMetricPanel
          chipId={chipId}
          topologyId={topologyId}
          metricKey={config.metric}
          selectionMode={config.selection_mode}
        />
      );
    }
    case "coupling_metric": {
      const config = readMetricConfig(panel);
      return (
        <CouplingMetricPanel
          chipId={chipId}
          topologyId={topologyId}
          metricKey={config.metric}
          selectionMode={config.selection_mode}
        />
      );
    }
    case "metric_script":
      return (
        <MetricScriptPanel
          panel={panel}
          chipId={chipId}
          topologyId={topologyId}
          editing={editing}
          onUpdateRevision={() => onCommand(panel.panel_id, "update-revision")}
        />
      );
    case "markdown":
      return <MarkdownPanel content={readMarkdownContent(panel)} />;
  }
}

interface DashboardPanelCardProps {
  /** The panel, with the script annotations the API adds to `metric_script` panels. */
  panel: DashboardPanelResponse;
  chipId: string;
  topologyId: string;
  editing: boolean;
  onCommand: (panelId: string, command: PanelCommand) => void;
}

/**
 * One panel on the 12-column grid. From `md` up it sits at its stored
 * position; below that panels stack full width in reading order.
 */
export function DashboardPanelCard({
  panel,
  chipId,
  topologyId,
  editing,
  onCommand,
}: DashboardPanelCardProps) {
  const { x, y, w, h } = panel.layout;
  const meta = panelTypeMeta(panel.type);
  const Icon = meta.icon;
  const title = panel.title || meta.label;
  const style = {
    "--panel-col": `${x + 1} / span ${w}`,
    "--panel-row": `${y + 1} / span ${h}`,
    "--panel-height": `${panelHeightPx(h)}px`,
  } as CSSProperties;

  return (
    <section
      aria-label={title}
      data-panel-id={panel.panel_id}
      style={style}
      className={`card card-border card-sm h-[var(--panel-height)] min-w-0 bg-base-100 md:h-auto md:[grid-column:var(--panel-col)] md:[grid-row:var(--panel-row)] ${
        editing ? "border-primary/30" : ""
      }`}
    >
      <div className="card-body min-h-0 gap-2 p-3">
        <header className="flex min-h-8 items-center gap-2">
          <Icon className="h-4 w-4 shrink-0 text-base-content/60" aria-hidden="true" />
          <h2 className="card-title min-w-0 flex-1 truncate text-sm">{title}</h2>
          {editing && (
            <>
              <span className="shrink-0 font-mono text-xs text-base-content/50">
                {w}×{h} at {x},{y}
              </span>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm btn-square"
                    aria-label={`Panel actions for ${title}`}
                  >
                    <EllipsisVertical className="h-4 w-4" aria-hidden="true" />
                  </button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onSelect={() => onCommand(panel.panel_id, "edit")}>
                    <Pencil className="h-4 w-4" aria-hidden="true" />
                    Edit panel
                  </DropdownMenuItem>
                  <DropdownMenuItem onSelect={() => onCommand(panel.panel_id, "duplicate")}>
                    <Copy className="h-4 w-4" aria-hidden="true" />
                    Duplicate panel
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuLabel>Layout</DropdownMenuLabel>
                  {LAYOUT_ITEMS.map((item) => {
                    const ItemIcon = item.icon;
                    return (
                      <DropdownMenuItem
                        key={item.action}
                        disabled={!canApplyLayoutAction(panel.layout, item.action)}
                        // Keep the menu open so several steps can be applied in a row.
                        onSelect={(event) => {
                          event.preventDefault();
                          onCommand(panel.panel_id, item.action);
                        }}
                      >
                        <ItemIcon className="h-4 w-4" aria-hidden="true" />
                        {item.label}
                      </DropdownMenuItem>
                    );
                  })}
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    className="text-error data-[highlighted]:text-error"
                    onSelect={() => onCommand(panel.panel_id, "remove")}
                  >
                    <Trash2 className="h-4 w-4" aria-hidden="true" />
                    Remove panel
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </>
          )}
        </header>
        <div className="min-h-0 flex-1">
          <PanelBody
            panel={panel}
            chipId={chipId}
            topologyId={topologyId}
            editing={editing}
            onCommand={onCommand}
          />
        </div>
      </div>
    </section>
  );
}
