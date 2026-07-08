"use client";

import Link from "next/link";

import { useQuery } from "@tanstack/react-query";
import type React from "react";
import { AlertTriangle, CalendarClock, Cpu, Plus, Tags, User, Users, Workflow } from "lucide-react";

import type { FlowSummary } from "@/schemas";

import { listFlows } from "@/client/flow/flow";
import { FlowSchedulesSection } from "@/components/features/flow/FlowSchedulesSection";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { WorkflowListPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";
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
        <h2 className="truncate text-base font-semibold">{flow.name}</h2>
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
        <FlowMetaItem
          icon={<User className="h-3.5 w-3.5" />}
          label="Creator"
          value={flow.created_by}
        />
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
            <th className="whitespace-nowrap">Creator</th>
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
                  className="block truncate font-semibold text-primary hover:underline"
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
              <td className="whitespace-nowrap">{flow.created_by}</td>
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

export function WorkflowPageContent() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["flows"],
    queryFn: () => listFlows(),
  });

  if (isLoading) {
    return <WorkflowListPageSkeleton />;
  }

  if (error) {
    return (
      <PageContainer>
        <div className="alert alert-error">
          <span>Failed to load flows: {(error as Error)?.message}</span>
        </div>
      </PageContainer>
    );
  }

  const flows = data?.data?.flows || [];
  const tagCount = new Set(flows.flatMap((flow) => flow.tags || [])).size;
  const creatorCount = new Set(flows.map((flow) => flow.created_by)).size;

  return (
    <PageContainer maxWidth>
      <PageHeader
        title="Project Workflows"
        description="Create, run, and schedule workflow definitions shared by this project."
        actions={
          <Link href="/workflow/new" className="btn btn-primary">
            <Plus size={20} />
            New Flow
          </Link>
        }
      />

      {flows.length > 0 && (
        <div className="mb-6 grid grid-cols-1 gap-3 sm:grid-cols-3 sm:gap-4">
          <div className="stat bg-base-200 rounded-box p-4">
            <div className="stat-figure text-primary">
              <Workflow className="h-6 w-6 sm:h-8 sm:w-8" />
            </div>
            <div className="stat-title text-xs sm:text-sm">Workflows</div>
            <div className="stat-value text-lg sm:text-2xl text-primary">{flows.length}</div>
            <div className="stat-desc text-xs">Defined for this project</div>
          </div>
          <div className="stat bg-base-200 rounded-box p-4">
            <div className="stat-figure text-secondary">
              <Users className="h-6 w-6 sm:h-8 sm:w-8" />
            </div>
            <div className="stat-title text-xs sm:text-sm">Creators</div>
            <div className="stat-value text-lg sm:text-2xl text-secondary">{creatorCount}</div>
            <div className="stat-desc text-xs">Distinct authors</div>
          </div>
          <div className="stat bg-base-200 rounded-box p-4">
            <div className="stat-figure text-accent">
              <Tags className="h-6 w-6 sm:h-8 sm:w-8" />
            </div>
            <div className="stat-title text-xs sm:text-sm">Tags</div>
            <div className="stat-value text-lg sm:text-2xl text-accent">{tagCount}</div>
            <div className="stat-desc text-xs">Unique labels in use</div>
          </div>
        </div>
      )}

      {flows.length === 0 ? (
        <div className="card bg-base-200 shadow-lg">
          <div className="card-body">
            <EmptyState
              title="No flows yet"
              description="Create a project workflow to start running shared calibrations."
              emoji="rocket"
              size="lg"
              action={
                <Link href="/workflow/new" className="btn btn-primary">
                  <Plus size={20} />
                  Create Flow
                </Link>
              }
            />
          </div>
        </div>
      ) : (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div className="min-w-0 space-y-4">
            <div className="card bg-base-200 shadow-lg hidden lg:block">
              <div className="card-body">
                <h2 className="card-title">Flow List</h2>
                <FlowTable flows={flows} />
              </div>
            </div>
            <div className="grid grid-cols-1 gap-3 lg:hidden">
              {flows.map((flow) => (
                <FlowCard key={flow.name} flow={flow} />
              ))}
            </div>
          </div>
          <FlowSchedulesSection />
        </div>
      )}
    </PageContainer>
  );
}
