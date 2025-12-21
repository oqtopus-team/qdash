"use client";

import Link from "next/link";

import { useQuery } from "@tanstack/react-query";

import type { FlowSummary } from "@/schemas";

import { listFlows } from "@/client/flow/flow";
import { FlowSchedulesSection } from "@/components/features/flow/FlowSchedulesSection";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { WorkflowListPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";
import { formatDateTime } from "@/utils/datetime";

export default function FlowListPage() {
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

  return (
    <PageContainer>
      <PageHeader
        title="User Flows"
        description="Create and manage workflow configurations"
        actions={
          <Link href="/workflow/new" className="btn btn-primary">
            + New Flow
          </Link>
        }
      />

      {flows.length === 0 ? (
        <div className="card bg-base-200">
          <div className="card-body items-center text-center">
            <h2 className="card-title">No flows yet</h2>
            <p>Create your first custom flow to get started</p>
            <Link href="/workflow/new" className="btn btn-primary mt-4">
              Create Flow
            </Link>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {flows.map((flow: FlowSummary) => (
            <Link
              key={flow.name}
              href={`/workflow/${flow.name}`}
              className="card bg-base-100 shadow-xl hover:shadow-2xl transition-shadow"
            >
              <div className="card-body p-4 sm:p-6">
                <h2 className="card-title">{flow.name}</h2>
                <p className="text-sm opacity-70">
                  {flow.description || "No description"}
                </p>
                <div className="divider my-2"></div>
                <div className="text-xs opacity-60">
                  <p>
                    <strong>Function:</strong> {flow.flow_function_name}
                  </p>
                  <p>
                    <strong>Chip:</strong> {flow.chip_id}
                  </p>
                  <p>
                    <strong>Updated:</strong> {formatDateTime(flow.updated_at)}
                  </p>
                </div>
                {flow.tags && flow.tags.length > 0 && (
                  <div className="flex flex-wrap gap-1 mt-2">
                    {flow.tags.map((tag) => (
                      <span key={tag} className="badge badge-sm badge-outline">
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </Link>
          ))}
        </div>
      )}

      {/* Scheduled Flows Section */}
      {flows.length > 0 && (
        <div className="mt-8">
          <FlowSchedulesSection />
        </div>
      )}
    </PageContainer>
  );
}
