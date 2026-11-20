"use client";

import { type ReactNode, useMemo, useState } from "react";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { useQueryClient } from "@tanstack/react-query";
import { Copy, FileCode, Trash2 } from "lucide-react";

import {
  getListMetricScriptsQueryKey,
  useCopyMetricScript,
  useDeleteMetricScript,
  useListMetricScripts,
} from "@/client/metric-script/metric-script";
import type { MetricScriptSummary } from "@/schemas";
import { VisibilityBadge } from "@/components/features/custom-dashboards/VisibilityBadge";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorCard } from "@/components/ui/ErrorCard";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import { formatDateTime, formatRelativeTime } from "@/lib/utils/datetime";

import { countLabel } from "./format";

function StatusBadge({ script }: { script: MetricScriptSummary }) {
  if (script.status === "valid") {
    return (
      <span className="badge badge-success badge-soft badge-sm">Valid r{script.revision}</span>
    );
  }
  return (
    <span
      className="badge badge-warning badge-soft badge-sm"
      title={
        script.active_revision
          ? `r${script.revision} has errors; dashboards use r${script.active_revision}`
          : "No revision has validated yet"
      }
    >
      Invalid r{script.revision}
      {script.active_revision ? ` · active r${script.active_revision}` : ""}
    </span>
  );
}

function metricsSummary(script: MetricScriptSummary): string {
  const targets = Array.from(new Set(script.metrics.map((metric) => metric.target)));
  const count = countLabel(script.metrics.length, "metric");
  return targets.length > 0 ? `${count} · ${targets.join(", ")}` : count;
}

interface ScriptRowProps {
  script: MetricScriptSummary;
  canCopy: boolean;
  canDelete: boolean;
  copying: boolean;
  onCopy: () => void;
  onDelete: () => void;
}

function ScriptRow({ script, canCopy, canDelete, copying, onCopy, onDelete }: ScriptRowProps) {
  const href = `/custom-dashboards/scripts/${script.script_id}`;
  return (
    <li className="list-row items-center" data-script-id={script.script_id}>
      <div className="flex h-9 w-9 items-center justify-center rounded-[var(--radius-field)] bg-base-200 text-base-content/60">
        <FileCode className="h-4 w-4" aria-hidden="true" />
      </div>
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <Link href={href} className="link link-hover truncate font-medium">
            {script.name}
          </Link>
          <VisibilityBadge visibility={script.visibility} />
          <StatusBadge script={script} />
        </div>
        {script.description && (
          <p className="mt-0.5 line-clamp-2 text-sm text-base-content/70">{script.description}</p>
        )}
        <p className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-base-content/60">
          <span>by {script.owner_username}</span>
          <span>{metricsSummary(script)}</span>
          <span title={formatDateTime(script.updated_at)}>
            Updated {formatRelativeTime(script.updated_at)}
          </span>
        </p>
      </div>
      <div className="flex shrink-0 items-center gap-1">
        <Link href={href} className="btn btn-sm">
          Open
        </Link>
        {canCopy && (
          <button
            type="button"
            className="btn btn-ghost btn-sm btn-square"
            onClick={onCopy}
            disabled={copying}
            aria-label={`Copy ${script.name}`}
            title="Copy to my scripts"
          >
            {copying ? (
              <span className="loading loading-spinner loading-xs" />
            ) : (
              <Copy className="h-4 w-4" aria-hidden="true" />
            )}
          </button>
        )}
        {canDelete && (
          <button
            type="button"
            className="btn btn-ghost btn-sm btn-square text-error"
            onClick={onDelete}
            aria-label={`Delete ${script.name}`}
            title="Delete"
          >
            <Trash2 className="h-4 w-4" aria-hidden="true" />
          </button>
        )}
      </div>
    </li>
  );
}

function ScriptGroup({
  title,
  emptyText,
  scripts,
  renderRow,
}: {
  title: string;
  emptyText: string;
  scripts: MetricScriptSummary[];
  renderRow: (script: MetricScriptSummary) => ReactNode;
}) {
  const headingId = `metric-scripts-${title.toLowerCase().replace(/\W+/g, "-")}`;
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2">
      <h2 id={headingId} className="flex items-center gap-2 text-sm font-medium">
        {title}
        <span className="badge badge-ghost badge-sm">{scripts.length}</span>
      </h2>
      {scripts.length > 0 ? (
        <ul className="list rounded-[var(--radius-box)] border border-base-content/10 bg-base-100">
          {scripts.map(renderRow)}
        </ul>
      ) : (
        <p className="rounded-[var(--radius-box)] border border-dashed border-base-300 px-4 py-3 text-sm text-base-content/60">
          {emptyText}
        </p>
      )}
    </section>
  );
}

/** Metric scripts the caller owns and those shared with the project, with copy and delete. */
export function MetricScriptList({ newButton }: { newButton: ReactNode }) {
  const router = useRouter();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { canEdit } = useProject();

  const { data, isLoading, isError, error, refetch, isRefetching } = useListMetricScripts();
  const copyMutation = useCopyMetricScript();
  const deleteMutation = useDeleteMetricScript();
  const [pendingDelete, setPendingDelete] = useState<MetricScriptSummary | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const { mine, shared } = useMemo(() => {
    const scripts = data?.data.scripts ?? [];
    const own = scripts.filter(
      (script) => !!user?.user_id && script.owner_user_id === user.user_id,
    );
    const others = scripts.filter((script) => !own.includes(script));
    return { mine: own, shared: others };
  }, [data, user?.user_id]);

  const invalidateList = () =>
    queryClient.invalidateQueries({ queryKey: getListMetricScriptsQueryKey() });

  const handleCopy = (script: MetricScriptSummary) => {
    copyMutation.mutate(
      { scriptId: script.script_id },
      {
        onSuccess: (response) => {
          void invalidateList();
          const copyId = response.data.script_id;
          toast.success(`Copied as "${response.data.name}"`, {
            action: {
              label: "Open",
              onClick: () => router.push(`/custom-dashboards/scripts/${copyId}`),
            },
          });
        },
        onError: (mutationError) =>
          toast.error(getApiErrorMessage(mutationError, "Failed to copy the script")),
      },
    );
  };

  const handleDelete = () => {
    if (!pendingDelete) return;
    setDeleteError(null);
    deleteMutation.mutate(
      { scriptId: pendingDelete.script_id },
      {
        onSuccess: () => {
          void invalidateList();
          toast.success("Script deleted");
          setPendingDelete(null);
        },
        // A 409 names the dashboards that still use the script; keep it in the dialog.
        onError: (mutationError) =>
          setDeleteError(getApiErrorMessage(mutationError, "Failed to delete the script")),
      },
    );
  };

  const renderRow = (script: MetricScriptSummary) => (
    <ScriptRow
      key={script.script_id}
      script={script}
      canCopy={canEdit && script.active_revision !== null}
      canDelete={canEdit && script.can_edit}
      copying={copyMutation.isPending && copyMutation.variables?.scriptId === script.script_id}
      onCopy={() => handleCopy(script)}
      onDelete={() => {
        setDeleteError(null);
        setPendingDelete(script);
      }}
    />
  );

  if (isLoading) {
    return (
      <div className="flex flex-col gap-2" aria-busy="true" aria-label="Loading scripts">
        {[0, 1, 2].map((index) => (
          <div key={index} className="skeleton h-16 w-full" />
        ))}
      </div>
    );
  }
  if (isError) {
    return (
      <ErrorCard
        title="Failed to load metric scripts"
        message={getApiErrorMessage(error, "The script list could not be loaded")}
        onRetry={() => void refetch()}
        retrying={isRefetching}
      />
    );
  }

  return (
    <>
      {mine.length + shared.length === 0 ? (
        <EmptyState
          emoji="chart"
          title="No metric scripts yet"
          description={
            canEdit
              ? "Write a Python script that computes per-qubit or per-pair values for dashboards"
              : "Scripts that project members share will appear here"
          }
          action={newButton}
        />
      ) : (
        <div className="flex flex-col gap-6">
          <ScriptGroup
            title="My scripts"
            emptyText="You have no scripts of your own"
            scripts={mine}
            renderRow={renderRow}
          />
          <ScriptGroup
            title="Shared scripts"
            emptyText="No other member has shared a script"
            scripts={shared}
            renderRow={renderRow}
          />
        </div>
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete metric script"
        description={
          pendingDelete ? (
            <>
              <span className="block">
                Delete &quot;{pendingDelete.name}&quot;? A script that a dashboard uses cannot be
                deleted.
              </span>
              {deleteError && (
                <span role="alert" className="alert alert-error alert-soft mt-3 text-sm">
                  {deleteError}
                </span>
              )}
            </>
          ) : (
            ""
          )
        }
        confirmLabel="Delete"
        destructive
        pending={deleteMutation.isPending}
        onOpenChange={(open) => {
          if (!open) {
            setPendingDelete(null);
            setDeleteError(null);
          }
        }}
        onConfirm={handleDelete}
      />
    </>
  );
}
