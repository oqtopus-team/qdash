"use client";

import { type ReactNode, useMemo, useState } from "react";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { useQueryClient } from "@tanstack/react-query";
import { Copy, Plus, Trash2 } from "lucide-react";
import { parseAsStringLiteral, useQueryState } from "nuqs";

import {
  getListCustomDashboardsQueryKey,
  useCreateCustomDashboard,
  useDeleteCustomDashboard,
  useDuplicateCustomDashboard,
  useListCustomDashboards,
} from "@/client/custom-dashboard/custom-dashboard";
import type { CustomDashboardResponse } from "@/schemas";
import { countLabel } from "@/components/features/metric-scripts/format";
import { MetricScriptList } from "@/components/features/metric-scripts/MetricScriptList";
import { NewMetricScriptDialog } from "@/components/features/metric-scripts/NewMetricScriptDialog";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorCard } from "@/components/ui/ErrorCard";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { useToast } from "@/components/ui/Toast";
import { useAuth } from "@/contexts/AuthContext";
import { useProject } from "@/contexts/ProjectContext";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import { formatDateTime, formatRelativeTime } from "@/lib/utils/datetime";

import { DashboardFormDialog, type DashboardFormValues } from "./DashboardFormDialog";
import { VisibilityLabel } from "./VisibilityLabel";

interface DashboardRowProps {
  dashboard: CustomDashboardResponse;
  canDuplicate: boolean;
  canDelete: boolean;
  duplicating: boolean;
  onDuplicate: () => void;
  onDelete: () => void;
}

function DashboardRow({
  dashboard,
  canDuplicate,
  canDelete,
  duplicating,
  onDuplicate,
  onDelete,
}: DashboardRowProps) {
  const href = `/custom-dashboards/${dashboard.dashboard_id}`;
  return (
    <li
      className="flex items-start gap-3 px-4 py-3 sm:items-center"
      data-dashboard-id={dashboard.dashboard_id}
    >
      <div className="min-w-0 flex-1">
        <Link href={href} className="link link-hover block truncate font-medium">
          {dashboard.name}
        </Link>
        {dashboard.description && (
          <p className="mt-0.5 line-clamp-2 text-xs text-base-content/70">
            {dashboard.description}
          </p>
        )}
        <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-base-content/60">
          <VisibilityLabel visibility={dashboard.visibility} />
          <span>by {dashboard.owner_username}</span>
          <span>{countLabel(dashboard.panels.length, "panel")}</span>
          {dashboard.chip_id && <span className="font-mono">{dashboard.chip_id}</span>}
          <span title={formatDateTime(dashboard.updated_at)}>
            Updated {formatRelativeTime(dashboard.updated_at)}
          </span>
        </p>
      </div>
      {(canDuplicate || canDelete) && (
        <div className="flex shrink-0 items-center gap-1">
          {canDuplicate && (
            <button
              type="button"
              className="btn btn-ghost btn-sm btn-square"
              onClick={onDuplicate}
              disabled={duplicating}
              aria-label={`Duplicate ${dashboard.name}`}
              title="Duplicate"
            >
              {duplicating ? (
                <span className="loading loading-spinner loading-xs" />
              ) : (
                <Copy className="h-4 w-4" aria-hidden="true" />
              )}
            </button>
          )}
          {canDelete && (
            <button
              type="button"
              className="btn btn-ghost btn-sm btn-square"
              onClick={onDelete}
              aria-label={`Delete ${dashboard.name}`}
              title="Delete"
            >
              <Trash2 className="h-4 w-4" aria-hidden="true" />
            </button>
          )}
        </div>
      )}
    </li>
  );
}

function DashboardGroup({
  title,
  emptyText,
  dashboards,
  renderRow,
}: {
  title: string;
  emptyText: string;
  dashboards: CustomDashboardResponse[];
  renderRow: (dashboard: CustomDashboardResponse) => ReactNode;
}) {
  const headingId = `custom-dashboards-${title.toLowerCase().replace(/\W+/g, "-")}`;
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2">
      <h2 id={headingId} className="text-sm font-medium">
        {title}
        <span className="ml-2 text-xs font-normal text-base-content/60">{dashboards.length}</span>
      </h2>
      {dashboards.length > 0 ? (
        <ul className="divide-y divide-base-content/10 rounded-[var(--radius-box)] border border-base-content/10 bg-base-100">
          {dashboards.map(renderRow)}
        </ul>
      ) : (
        <p className="text-xs text-base-content/60">{emptyText}</p>
      )}
    </section>
  );
}

const TABS = ["dashboards", "scripts"] as const;
type ListTab = (typeof TABS)[number];

const TAB_LABELS: Record<ListTab, string> = { dashboards: "Dashboards", scripts: "Scripts" };

/**
 * Dashboards the caller owns and those shared with the project, and on the Scripts tab the
 * metric scripts their panels evaluate.
 */
export function CustomDashboardListPageContent() {
  const router = useRouter();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const { canEdit } = useProject();
  const [tab, setTab] = useQueryState("tab", parseAsStringLiteral(TABS).withDefault("dashboards"));
  const [newScriptOpen, setNewScriptOpen] = useState(false);

  const { data, isLoading, isError, error, refetch, isRefetching } = useListCustomDashboards();
  const createMutation = useCreateCustomDashboard();
  const duplicateMutation = useDuplicateCustomDashboard();
  const deleteMutation = useDeleteCustomDashboard();

  const [createOpen, setCreateOpen] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [pendingDelete, setPendingDelete] = useState<CustomDashboardResponse | null>(null);

  const { mine, shared } = useMemo(() => {
    const dashboards = data?.data.dashboards ?? [];
    const own = dashboards.filter(
      (dashboard) => !!user?.user_id && dashboard.owner_user_id === user.user_id,
    );
    const others = dashboards.filter(
      (dashboard) => dashboard.visibility === "project" && !own.includes(dashboard),
    );
    return { mine: own, shared: others };
  }, [data, user?.user_id]);

  const invalidateList = () =>
    queryClient.invalidateQueries({ queryKey: getListCustomDashboardsQueryKey() });

  const handleCreate = (values: DashboardFormValues) => {
    setCreateError(null);
    createMutation.mutate(
      { data: { ...values, panels: [] } },
      {
        onSuccess: (response) => {
          void invalidateList();
          setCreateOpen(false);
          toast.success("Dashboard created");
          router.push(`/custom-dashboards/${response.data.dashboard_id}`);
        },
        onError: (mutationError) =>
          setCreateError(getApiErrorMessage(mutationError, "Failed to create the dashboard")),
      },
    );
  };

  const handleDuplicate = (dashboard: CustomDashboardResponse) => {
    duplicateMutation.mutate(
      { dashboardId: dashboard.dashboard_id },
      {
        onSuccess: (response) => {
          void invalidateList();
          const copyId = response.data.dashboard_id;
          toast.success(`Duplicated as "${response.data.name}"`, {
            action: {
              label: "Open",
              onClick: () => router.push(`/custom-dashboards/${copyId}`),
            },
          });
        },
        onError: (mutationError) =>
          toast.error(getApiErrorMessage(mutationError, "Failed to duplicate the dashboard")),
      },
    );
  };

  const handleDelete = () => {
    if (!pendingDelete) return;
    deleteMutation.mutate(
      { dashboardId: pendingDelete.dashboard_id },
      {
        onSuccess: () => {
          void invalidateList();
          toast.success("Dashboard deleted");
          setPendingDelete(null);
        },
        onError: (mutationError) => {
          toast.error(getApiErrorMessage(mutationError, "Failed to delete the dashboard"));
          setPendingDelete(null);
        },
      },
    );
  };

  const renderRow = (dashboard: CustomDashboardResponse) => (
    <DashboardRow
      key={dashboard.dashboard_id}
      dashboard={dashboard}
      canDuplicate={canEdit}
      canDelete={canEdit && dashboard.can_edit}
      duplicating={
        duplicateMutation.isPending &&
        duplicateMutation.variables?.dashboardId === dashboard.dashboard_id
      }
      onDuplicate={() => handleDuplicate(dashboard)}
      onDelete={() => setPendingDelete(dashboard)}
    />
  );

  const newButton = canEdit ? (
    <button
      type="button"
      className="btn btn-primary btn-sm"
      onClick={() => {
        setCreateError(null);
        setCreateOpen(true);
      }}
    >
      <Plus data-icon="inline-start" aria-hidden="true" />
      New dashboard
    </button>
  ) : null;

  const newScriptButton = canEdit ? (
    <button type="button" className="btn btn-primary btn-sm" onClick={() => setNewScriptOpen(true)}>
      <Plus data-icon="inline-start" aria-hidden="true" />
      New script
    </button>
  ) : null;

  const total = mine.length + shared.length;

  return (
    <PageContainer maxWidth>
      <PageHeader
        title="Dashboards"
        description={
          tab === "scripts"
            ? "Python metric scripts that compute per-qubit and per-pair values for panels"
            : "Panels composed by project members, private or shared with the project"
        }
        actions={tab === "scripts" ? newScriptButton : newButton}
      />

      <div
        role="tablist"
        aria-label="Dashboards and scripts"
        className="tabs tabs-border mb-4 w-fit"
      >
        {TABS.map((value) => (
          <button
            key={value}
            type="button"
            role="tab"
            id={`custom-dashboards-tab-${value}`}
            aria-selected={tab === value}
            aria-controls="custom-dashboards-tabpanel"
            className={`tab ${tab === value ? "tab-active" : ""}`}
            onClick={() => void setTab(value === "dashboards" ? null : value)}
          >
            {TAB_LABELS[value]}
          </button>
        ))}
      </div>

      <div
        role="tabpanel"
        id="custom-dashboards-tabpanel"
        aria-labelledby={`custom-dashboards-tab-${tab}`}
      >
        {tab === "scripts" ? (
          <MetricScriptList newButton={newScriptButton} />
        ) : isLoading ? (
          <div className="flex flex-col gap-2" aria-busy="true" aria-label="Loading dashboards">
            {[0, 1, 2].map((index) => (
              <div key={index} className="skeleton h-16 w-full" />
            ))}
          </div>
        ) : isError ? (
          <ErrorCard
            title="Failed to load dashboards"
            message={getApiErrorMessage(error, "The dashboard list could not be loaded")}
            onRetry={() => void refetch()}
            retrying={isRefetching}
          />
        ) : total === 0 ? (
          <EmptyState
            emoji="chart"
            title="No dashboards yet"
            description={
              canEdit
                ? "Create a dashboard and add metric, metric script and note panels"
                : "Dashboards that project members share will appear here"
            }
            action={newButton}
          />
        ) : (
          <div className="flex flex-col gap-6">
            <DashboardGroup
              title="Mine"
              emptyText="You have no dashboards of your own"
              dashboards={mine}
              renderRow={renderRow}
            />
            <DashboardGroup
              title="Shared with project"
              emptyText="No other member has shared a dashboard"
              dashboards={shared}
              renderRow={renderRow}
            />
          </div>
        )}
      </div>

      {canEdit && <NewMetricScriptDialog open={newScriptOpen} onOpenChange={setNewScriptOpen} />}

      {canEdit && (
        <DashboardFormDialog
          open={createOpen}
          mode="create"
          pending={createMutation.isPending}
          error={createError}
          onOpenChange={setCreateOpen}
          onSubmit={handleCreate}
        />
      )}

      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete dashboard"
        description={
          pendingDelete
            ? `Delete "${pendingDelete.name}"? Project members it is shared with lose access too.`
            : ""
        }
        confirmLabel="Delete"
        destructive
        pending={deleteMutation.isPending}
        onOpenChange={(open) => !open && setPendingDelete(null)}
        onConfirm={handleDelete}
      />
    </PageContainer>
  );
}
