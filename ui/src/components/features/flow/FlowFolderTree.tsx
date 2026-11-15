"use client";

import Link from "next/link";
import type React from "react";
import { useEffect, useRef } from "react";
import {
  AlertTriangle,
  CalendarClock,
  ChevronRight,
  Cpu,
  Folder,
  FolderOpen,
  PanelLeftOpen,
  Tags,
  Trash2,
  Workflow,
} from "lucide-react";

import type { FlowSummary } from "@/schemas";

import { countFlows, type FlowFolder, type FlowTreeNode } from "@/lib/flowFolders";
import { formatDateTime } from "@/lib/utils/datetime";

/**
 * Selection and deletion controls for the listed flows. Absent for users who
 * cannot delete flows, in which case the list renders read-only.
 */
export interface FlowSelection {
  selected: ReadonlySet<string>;
  /** True while a deletion is in progress; every control is disabled. */
  disabled: boolean;
  onToggle: (name: string) => void;
  /** Select (true) or deselect (false) every named flow, leaving the rest of the selection as is. */
  onSetMany: (names: readonly string[], selected: boolean) => void;
  onDelete: (name: string) => void;
}

function FlowSelectCheckbox({ flow, selection }: { flow: FlowSummary; selection: FlowSelection }) {
  return (
    <input
      type="checkbox"
      className="checkbox checkbox-sm"
      aria-label={`Select workflow ${flow.name}`}
      checked={selection.selected.has(flow.name)}
      disabled={selection.disabled}
      onChange={() => selection.onToggle(flow.name)}
    />
  );
}

/**
 * Selects or deselects every workflow of one creator, including flows in
 * subfolders and in a closed folder. Mixed when only some of them are selected.
 */
function FolderSelectCheckbox({
  folder,
  selection,
}: {
  folder: FlowFolder;
  selection: FlowSelection;
}) {
  const names = folder.flows.map((flow) => flow.name);
  const selectedCount = names.filter((name) => selection.selected.has(name)).length;
  const all = names.length > 0 && selectedCount === names.length;
  const some = selectedCount > 0 && !all;
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.indeterminate = some;
  }, [some]);
  return (
    <input
      ref={ref}
      type="checkbox"
      className="checkbox checkbox-sm"
      aria-label={`Select all workflows by ${folder.creator}`}
      checked={all}
      disabled={selection.disabled || names.length === 0}
      onChange={() => selection.onSetMany(names, !all)}
    />
  );
}

function FlowDeleteButton({ flow, selection }: { flow: FlowSummary; selection: FlowSelection }) {
  return (
    <button
      type="button"
      className="btn btn-ghost btn-xs btn-square text-error"
      aria-label={`Delete workflow ${flow.name}`}
      title={`Delete ${flow.name}`}
      disabled={selection.disabled}
      onClick={() => selection.onDelete(flow.name)}
    >
      <Trash2 className="h-4 w-4" />
    </button>
  );
}

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

function FlowCard({ flow, selection }: { flow: FlowSummary; selection?: FlowSelection }) {
  return (
    <div className="relative rounded-lg border border-base-300 bg-base-100 p-4 transition-colors hover:border-primary/50">
      <div className="flex min-w-0 items-center gap-2">
        {selection && (
          <span className="relative z-10 flex">
            <FlowSelectCheckbox flow={flow} selection={selection} />
          </span>
        )}
        <h2 className="truncate text-sm font-medium">
          {/* The link covers the whole card; the selection and delete controls sit above it. */}
          <Link href={`/workflow/${flow.name}`} className="after:absolute after:inset-0">
            {flow.name}
          </Link>
        </h2>
        {flow.file_exists === false && (
          <span
            className="badge badge-warning badge-sm shrink-0 gap-1"
            title="Source file is missing"
          >
            <AlertTriangle className="h-3 w-3" />
            Missing
          </span>
        )}
        {selection && (
          <span className="relative z-10 ml-auto shrink-0">
            <FlowDeleteButton flow={flow} selection={selection} />
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
    </div>
  );
}

function FlowTable({ flows, selection }: { flows: FlowSummary[]; selection?: FlowSelection }) {
  return (
    <div className="overflow-x-auto">
      <table className="table table-zebra">
        <thead>
          <tr>
            {selection && (
              <th className="w-8">
                <span className="sr-only">Select</span>
              </th>
            )}
            <th className="min-w-[200px]">Name</th>
            <th className="whitespace-nowrap">Chip</th>
            <th className="whitespace-nowrap">Function</th>
            <th>Tags</th>
            <th className="whitespace-nowrap text-right">Updated</th>
            {selection && (
              <th className="w-8">
                <span className="sr-only">Actions</span>
              </th>
            )}
          </tr>
        </thead>
        <tbody>
          {flows.map((flow) => (
            <tr key={flow.name} className="align-top">
              {selection && (
                <td>
                  <FlowSelectCheckbox flow={flow} selection={selection} />
                </td>
              )}
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
              {selection && (
                <td className="text-right">
                  <FlowDeleteButton flow={flow} selection={selection} />
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** The flows of one folder, as a table on large screens and cards below. */
function FlowList({ flows, selection }: { flows: FlowSummary[]; selection?: FlowSelection }) {
  return (
    <>
      <div className="hidden lg:block">
        <FlowTable flows={flows} selection={selection} />
      </div>
      <div className="grid grid-cols-1 gap-3 lg:hidden">
        {flows.map((flow) => (
          <FlowCard key={flow.name} flow={flow} selection={selection} />
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
function FlowTreeView({ node, selection }: { node: FlowTreeNode; selection?: FlowSelection }) {
  return (
    <div className="space-y-3">
      {node.flows.length > 0 && <FlowList flows={node.flows} selection={selection} />}
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
            <FlowTreeView node={child} selection={selection} />
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
 * editor's Explorer, where folders are made, renamed and moved. With a
 * selection, a checkbox beside the header selects all of the creator's workflows.
 */
export function FlowFolderSection({
  folder,
  selection,
}: {
  folder: FlowFolder;
  selection?: FlowSelection;
}) {
  const count = folder.flows.length;
  return (
    <div className="card relative bg-base-200 shadow-sm">
      {/* The folder checkbox sits beside the disclosure, not inside its summary, so selecting
          a creator's workflows never opens or closes the folder. */}
      {selection && (
        <span className="absolute left-4 top-3 z-10 flex h-6 items-center sm:left-6">
          <FolderSelectCheckbox folder={folder} selection={selection} />
        </span>
      )}
      <details open={folder.mine} className="group" data-testid={`flow-folder-${folder.creator}`}>
        <summary
          className={`flex cursor-pointer select-none items-center gap-2 py-3 pr-4 sm:pr-6 [&::-webkit-details-marker]:hidden ${
            selection ? "pl-11 sm:pl-13" : "pl-4 sm:pl-6"
          }`}
        >
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
          <FlowTreeView node={folder.root} selection={selection} />
        </div>
      </details>
    </div>
  );
}
