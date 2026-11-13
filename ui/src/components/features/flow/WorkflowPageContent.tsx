"use client";

import Link from "next/link";
import { useMemo, useState } from "react";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, RotateCcw, Trash2, X } from "lucide-react";

import { deleteFlow, listFlows } from "@/client/flow/flow";
import { FlowFolderSection, type FlowSelection } from "@/components/features/flow/FlowFolderTree";
import { FlowSchedulesSection } from "@/components/features/flow/FlowSchedulesSection";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { WorkflowListPageSkeleton } from "@/components/ui/Skeleton/PageSkeletons";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";
import { deleteFlowsSequentially, type FlowDeletionFailure } from "@/lib/flowDeletion";
import { groupFlowsByCreator } from "@/lib/flowFolders";

function workflowCount(count: number): string {
  return `${count} ${count === 1 ? "workflow" : "workflows"}`;
}

export function WorkflowPageContent() {
  const { username } = useAuth();
  const { canEdit } = useProject();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { data, isLoading, error } = useQuery({
    queryKey: ["flows"],
    queryFn: () => listFlows(),
  });

  const [selected, setSelected] = useState<ReadonlySet<string>>(() => new Set());
  // Flows waiting for confirmation in the delete dialog.
  const [confirmTargets, setConfirmTargets] = useState<string[] | null>(null);
  const [progress, setProgress] = useState(0);
  const [failures, setFailures] = useState<FlowDeletionFailure[]>([]);

  const deleteMutation = useMutation({
    mutationFn: (names: string[]) => {
      setProgress(0);
      return deleteFlowsSequentially(names, (name) => deleteFlow(name), setProgress);
    },
    onSuccess: async ({ deleted, failed }, names) => {
      // Earlier failures outside this attempt stay listed; this attempt's outcome replaces its own.
      setFailures((current) => [
        ...current.filter((failure) => !names.includes(failure.name)),
        ...failed,
      ]);
      // Deleted flows leave the selection; flows that failed stay selected for a retry.
      setSelected((current) => {
        const next = new Set(current);
        for (const name of deleted) next.delete(name);
        return next;
      });
      setConfirmTargets(null);
      for (const name of deleted) {
        queryClient.removeQueries({ queryKey: ["flow", name] });
      }
      if (deleted.length > 0) {
        toast.success(
          deleted.length === 1 && names.length === 1
            ? `Deleted ${deleted[0]}`
            : `Deleted ${workflowCount(deleted.length)}`,
        );
      }
      if (failed.length > 0) {
        toast.error(`Failed to delete ${failed.length} of ${workflowCount(names.length)}`);
      }
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["flows"] }),
        queryClient.invalidateQueries({ queryKey: ["flow-schedules"] }),
      ]);
    },
  });
  const deleting = deleteMutation.isPending;

  const flows = useMemo(() => data?.data?.flows ?? [], [data]);
  const flowNames = useMemo(() => flows.map((flow) => flow.name), [flows]);
  // Only flows still listed count as selected, so a flow removed elsewhere drops out.
  const selectedNames = useMemo(
    () => flowNames.filter((name) => selected.has(name)),
    [flowNames, selected],
  );

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

  const tagCount = new Set(flows.flatMap((flow) => flow.tags || [])).size;
  const folders = groupFlowsByCreator(flows, username);

  const selection: FlowSelection | undefined = canEdit
    ? {
        selected,
        disabled: deleting,
        onToggle: (name) =>
          setSelected((current) => {
            const next = new Set(current);
            if (next.has(name)) next.delete(name);
            else next.add(name);
            return next;
          }),
        onSetMany: (names, select) =>
          setSelected((current) => {
            const next = new Set(current);
            for (const name of names) {
              if (select) next.add(name);
              else next.delete(name);
            }
            return next;
          }),
        onDelete: (name) => setConfirmTargets([name]),
      }
    : undefined;

  const closeConfirm = () => {
    if (!deleting) setConfirmTargets(null);
  };

  return (
    <PageContainer maxWidth>
      <PageHeader
        title="Workflow"
        description="Flow definitions shared by this project"
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
            <div className="stat-title text-sm">Workflows</div>
            <div className="stat-value">{flows.length}</div>
            <div className="stat-desc text-xs">Defined for this project</div>
          </div>
          <div className="stat bg-base-200 rounded-box p-4">
            <div className="stat-title text-sm">Creators</div>
            <div className="stat-value">{folders.length}</div>
            <div className="stat-desc text-xs">Distinct authors</div>
          </div>
          <div className="stat bg-base-200 rounded-box p-4">
            <div className="stat-title text-sm">Tags</div>
            <div className="stat-value">{tagCount}</div>
            <div className="stat-desc text-xs">Unique labels in use</div>
          </div>
        </div>
      )}

      {flows.length === 0 ? (
        <div className="card bg-base-200 shadow-sm">
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
            {canEdit && (
              <div className="flex flex-wrap items-center gap-2 rounded-box bg-base-200 px-4 py-3 sm:px-6">
                <span className="text-sm text-base-content/70" aria-live="polite">
                  {selectedNames.length} selected
                </span>
                <div className="ml-auto flex items-center gap-2">
                  {selectedNames.length > 0 && (
                    <button
                      type="button"
                      className="btn btn-ghost btn-sm"
                      disabled={deleting}
                      onClick={() => setSelected(new Set())}
                    >
                      <X className="h-4 w-4" />
                      Clear
                    </button>
                  )}
                  <button
                    type="button"
                    className="btn btn-error btn-sm"
                    disabled={deleting || selectedNames.length === 0}
                    onClick={() => setConfirmTargets(selectedNames)}
                  >
                    <Trash2 className="h-4 w-4" />
                    Delete selected
                  </button>
                </div>
              </div>
            )}

            {failures.length > 0 && (
              <div role="alert" className="alert alert-error alert-vertical sm:alert-horizontal">
                <div className="min-w-0">
                  <p className="text-sm font-medium">
                    Could not delete {workflowCount(failures.length)}
                  </p>
                  <ul className="mt-1 space-y-0.5 text-xs">
                    {failures.map((failure) => (
                      <li key={failure.name} className="break-words">
                        <span className="font-medium">{failure.name}</span>: {failure.message}
                      </li>
                    ))}
                  </ul>
                </div>
                <div className="flex gap-2">
                  <button
                    type="button"
                    className="btn btn-sm"
                    disabled={deleting}
                    onClick={() =>
                      setConfirmTargets(
                        failures
                          .map((failure) => failure.name)
                          .filter((name) => flowNames.includes(name)),
                      )
                    }
                  >
                    <RotateCcw className="h-4 w-4" />
                    Retry
                  </button>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    disabled={deleting}
                    onClick={() => setFailures([])}
                  >
                    Dismiss
                  </button>
                </div>
              </div>
            )}

            {folders.map((folder) => (
              <FlowFolderSection key={folder.creator} folder={folder} selection={selection} />
            ))}
          </div>
          <FlowSchedulesSection />
        </div>
      )}

      {confirmTargets && (
        <Dialog open onOpenChange={(open) => !open && closeConfirm()}>
          <DialogContent className="max-w-md">
            <DialogTitle>
              {confirmTargets.length === 1
                ? "Delete workflow"
                : `Delete ${workflowCount(confirmTargets.length)}`}
            </DialogTitle>
            <DialogDescription className="mt-2 text-sm text-base-content/70">
              Deleting a workflow removes its source file and saved definition. Removal of its
              Prefect deployment and schedules is also attempted; if that fails, schedules may
              remain active. Past executions are kept. This cannot be undone.
            </DialogDescription>
            <ul
              className="mt-3 max-h-48 space-y-1 overflow-y-auto rounded-box bg-base-200 p-3 text-sm"
              aria-label="Workflows to delete"
            >
              {confirmTargets.map((name) => (
                <li key={name} className="truncate font-medium">
                  {name}
                </li>
              ))}
            </ul>
            {deleting && confirmTargets.length > 1 && (
              <p className="mt-3 text-xs text-base-content/70" aria-live="polite">
                Processed {progress} of {confirmTargets.length}…
              </p>
            )}
            <div className="modal-action">
              <button
                type="button"
                className="btn btn-ghost"
                onClick={closeConfirm}
                disabled={deleting}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn btn-error"
                onClick={() => deleteMutation.mutate(confirmTargets)}
                disabled={deleting || confirmTargets.length === 0}
              >
                {deleting && <span className="loading loading-spinner loading-xs" />}
                {confirmTargets.length === 1
                  ? "Delete"
                  : `Delete ${workflowCount(confirmTargets.length)}`}
              </button>
            </div>
          </DialogContent>
        </Dialog>
      )}
    </PageContainer>
  );
}
