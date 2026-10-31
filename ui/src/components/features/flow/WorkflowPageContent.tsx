"use client";

import Link from "next/link";

import { useQuery } from "@tanstack/react-query";
import { Plus, Tags, Users, Workflow } from "lucide-react";

import { listFlows } from "@/client/flow/flow";
import { FlowFolderSection } from "@/components/features/flow/FlowFolderTree";
import { FlowSchedulesSection } from "@/components/features/flow/FlowSchedulesSection";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { WorkflowListPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";
import { useAuth } from "@/contexts/AuthContext";
import { groupFlowsByCreator } from "@/lib/flowFolders";

export function WorkflowPageContent() {
  const { username } = useAuth();
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
  const folders = groupFlowsByCreator(flows, username);

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
            <div className="stat-title text-sm">Workflows</div>
            <div className="stat-value text-primary">{flows.length}</div>
            <div className="stat-desc text-xs">Defined for this project</div>
          </div>
          <div className="stat bg-base-200 rounded-box p-4">
            <div className="stat-figure text-secondary">
              <Users className="h-6 w-6 sm:h-8 sm:w-8" />
            </div>
            <div className="stat-title text-sm">Creators</div>
            <div className="stat-value text-secondary">{folders.length}</div>
            <div className="stat-desc text-xs">Distinct authors</div>
          </div>
          <div className="stat bg-base-200 rounded-box p-4">
            <div className="stat-figure text-accent">
              <Tags className="h-6 w-6 sm:h-8 sm:w-8" />
            </div>
            <div className="stat-title text-sm">Tags</div>
            <div className="stat-value text-accent">{tagCount}</div>
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
            {folders.map((folder) => (
              <FlowFolderSection key={folder.creator} folder={folder} />
            ))}
          </div>
          <FlowSchedulesSection />
        </div>
      )}
    </PageContainer>
  );
}
