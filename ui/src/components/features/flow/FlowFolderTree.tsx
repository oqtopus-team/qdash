"use client";

import Link from "next/link";
import type React from "react";
import {
  AlertTriangle,
  CalendarClock,
  ChevronRight,
  Cpu,
  Folder,
  FolderOpen,
  PanelLeftOpen,
  Tags,
  Workflow,
} from "lucide-react";

import type { FlowSummary } from "@/schemas";

import { countFlows, type FlowFolder, type FlowTreeNode } from "@/lib/flowFolders";
import { formatDateTime } from "@/lib/utils/datetime";

function FlowMetaItem({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
}) {
  return (
    <div className="flex min-w-0 items-center gap-2 text-xs text-base-content/70">
      <span className="text-base-content/45">{icon}</span>
      <span className="shrink-0">{label}</span>
      <span className="min-w-0 truncate font-medium text-base-content">{value}</span>
    </div>
  );
}

function FlowCard({ flow }: { flow: FlowSummary }) {
  return (
    <Link
      href={`/workflow/${flow.name}`}
      className="block rounded-lg border border-base-300 bg-base-100 p-4 transition-colors hover:border-primary/50"
    >
      <div className="flex min-w-0 items-center gap-2">
        <h2 className="truncate text-sm font-medium">{flow.name}</h2>
        {flow.file_exists === false && (
          <span
            className="badge badge-warning badge-sm shrink-0 gap-1"
            title="Source file is missing"
          >
            <AlertTriangle className="h-3 w-3" />
            Missing
          </span>
        )}
      </div>
      <p className="mt-1 line-clamp-2 min-h-10 text-sm text-base-content/70">
        {flow.description || "No description"}
      </p>

      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        <FlowMetaItem icon={<Cpu className="h-3.5 w-3.5" />} label="Chip" value={flow.chip_id} />
        <FlowMetaItem
          icon={<CalendarClock className="h-3.5 w-3.5" />}
          label="Updated"
          value={formatDateTime(flow.updated_at)}
        />
        <FlowMetaItem
          icon={<Workflow className="h-3.5 w-3.5" />}
          label="Function"
          value={flow.flow_function_name}
        />
      </div>

      <div className="mt-4 flex min-h-6 flex-wrap gap-1.5">
        {flow.tags && flow.tags.length > 0 ? (
          flow.tags.map((tag) => (
            <span key={tag} className="badge badge-outline badge-sm">
              {tag}
            </span>
          ))
        ) : (
          <span className="inline-flex items-center gap-1 text-xs text-base-content/50">
            <Tags className="h-3.5 w-3.5" />
            No tags
          </span>
        )}
      </div>
    </Link>
  );
}

function FlowTable({ flows }: { flows: FlowSummary[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="table table-zebra">
        <thead>
          <tr>
            <th className="min-w-[200px]">Name</th>
            <th className="whitespace-nowrap">Chip</th>
            <th className="whitespace-nowrap">Function</th>
            <th>Tags</th>
            <th className="whitespace-nowrap text-right">Updated</th>
          </tr>
        </thead>
        <tbody>
          {flows.map((flow) => (
            <tr key={flow.name} className="align-top">
              <td className="max-w-[260px]">
                <Link
                  href={`/workflow/${flow.name}`}
                  className="block truncate font-medium text-primary hover:underline"
                >
                  {flow.name}
                </Link>
                {flow.file_exists === false && (
                  <div className="mt-1">
                    <span
                      className="badge badge-warning badge-xs gap-1"
                      title="Source file is missing"
                    >
                      <AlertTriangle className="h-3 w-3" />
                      Missing source file
                    </span>
                  </div>
                )}
                {flow.description && (
                  <div className="truncate text-xs text-base-content/60">{flow.description}</div>
                )}
              </td>
              <td className="whitespace-nowrap">{flow.chip_id}</td>
              <td className="max-w-[160px] truncate font-mono text-xs">
                {flow.flow_function_name}
              </td>
              <td>
                <div className="flex max-w-[200px] flex-wrap gap-1">
                  {flow.tags?.length ? (
                    flow.tags.map((tag) => (
                      <span key={tag} className="badge badge-outline badge-xs">
                        {tag}
                      </span>
                    ))
                  ) : (
                    <span className="text-xs text-base-content/50">None</span>
                  )}
                </div>
              </td>
              <td className="whitespace-nowrap text-right text-xs">
                {formatDateTime(flow.updated_at)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** The flows of one folder, as a table on large screens and cards below. */
function FlowList({ flows }: { flows: FlowSummary[] }) {
  return (
    <>
      <div className="hidden lg:block">
        <FlowTable flows={flows} />
      </div>
      <div className="grid grid-cols-1 gap-3 lg:hidden">
        {flows.map((flow) => (
          <FlowCard key={flow.name} flow={flow} />
        ))}
      </div>
    </>
  );
}

/**
 * A folder's own flows, then each subfolder as a nested, open disclosure.
 * Subfolders are the creator's own filing, so none starts closed. Filing is
 * done in the Workflow editor's Explorer; this page only shows the result.
 */
function FlowTreeView({ node }: { node: FlowTreeNode }) {
  return (
    <div className="space-y-3">
      {node.flows.length > 0 && <FlowList flows={node.flows} />}
      {node.children.map((child) => (
        <details
          key={child.path}
          open
          className="group/sub rounded-lg border border-base-300 bg-base-100"
          data-testid={`flow-subfolder-${child.path}`}
        >
          <summary className="flex cursor-pointer select-none items-center gap-2 px-3 py-2 text-sm [&::-webkit-details-marker]:hidden">
            <ChevronRight className="h-3.5 w-3.5 shrink-0 text-base-content/60 transition-transform group-open/sub:rotate-90" />
            <Folder className="h-4 w-4 shrink-0 text-base-content/70" />
            <span className="truncate font-medium">{child.name}</span>
            <span className="ml-auto shrink-0 text-xs text-base-content/60">
              {countFlows(child)}
            </span>
          </summary>
          <div className="px-3 pb-3">
            <FlowTreeView node={child} />
          </div>
        </details>
      ))}
    </div>
  );
}

/**
 * One creator's workflows behind a folder header. The signed-in user's folder
 * starts open and the others closed, so the list shows your own work first and
 * everyone else's a click away. "Open in editor" shows the same space in the
 * editor's Explorer, where folders are made, renamed and moved.
 */
export function FlowFolderSection({ folder }: { folder: FlowFolder }) {
  const count = folder.flows.length;
  return (
    <details
      open={folder.mine}
      className="group card bg-base-200 shadow-lg"
      data-testid={`flow-folder-${folder.creator}`}
    >
      <summary className="flex cursor-pointer select-none items-center gap-2 px-4 py-3 sm:px-6 [&::-webkit-details-marker]:hidden">
        <ChevronRight className="h-4 w-4 shrink-0 text-base-content/60 transition-transform group-open:rotate-90" />
        <FolderOpen className="h-5 w-5 shrink-0 text-primary" />
        <span className="truncate text-sm font-medium">{folder.creator}</span>
        {folder.mine && <span className="badge badge-primary badge-sm shrink-0">You</span>}
        <span className="ml-auto shrink-0 text-xs text-base-content/60">
          {count} {count === 1 ? "workflow" : "workflows"}
        </span>
        {folder.flows[0] && (
          <Link
            href={`/workflow/${encodeURIComponent(folder.flows[0].name)}?space=${encodeURIComponent(folder.creator)}`}
            className="btn btn-ghost btn-xs gap-1"
            title="Open this space in the editor's Explorer, where folders can be arranged"
            onClick={(event) => event.stopPropagation()}
          >
            <PanelLeftOpen className="h-4 w-4" />
            <span className="hidden sm:inline">Open in editor</span>
          </Link>
        )}
      </summary>
      <div className="px-4 pb-4 sm:px-6 sm:pb-6">
        <FlowTreeView node={folder.root} />
      </div>
    </details>
  );
}
