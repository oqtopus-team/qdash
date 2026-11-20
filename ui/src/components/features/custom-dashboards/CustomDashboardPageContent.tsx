"use client";

import { useEffect, useMemo, useState } from "react";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import {
  ArrowLeft,
  CircleAlert,
  Copy,
  EllipsisVertical,
  Link as LinkIcon,
  Lock,
  Pencil,
  Plus,
  RotateCcw,
  Save,
  Settings,
  Trash2,
  Users,
} from "lucide-react";
import { parseAsString, useQueryState } from "nuqs";

import {
  getGetCustomDashboardQueryKey,
  getListCustomDashboardsQueryKey,
  useDeleteCustomDashboard,
  useDuplicateCustomDashboard,
  useGetCustomDashboard,
  useUpdateCustomDashboard,
} from "@/client/custom-dashboard/custom-dashboard";
import type {
  CustomDashboardResponse,
  CustomDashboardUpdateRequest,
  DashboardPanelModel,
  DashboardPanelResponse,
} from "@/schemas";
import { ChipSelector } from "@/components/selectors/ChipSelector";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorCard } from "@/components/ui/ErrorCard";
import { PageContainer } from "@/components/ui/PageContainer";
import { useToast } from "@/components/ui/Toast";
import { useProject } from "@/contexts/ProjectContext";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import { copyText } from "@/lib/utils/clipboard";
import { formatDateTime, formatRelativeTime } from "@/lib/utils/datetime";
import {
  useChipTopologyId,
  useDefaultChipId,
} from "@/components/features/metric-scripts/useChipTopology";

import { DashboardFormDialog, type DashboardFormValues } from "./DashboardFormDialog";
import { DashboardPanelCard, type PanelCommand } from "./DashboardPanelCard";
import { applyLayoutAction, nextPanelLayout, resolveCollisions, sortPanels } from "./layout";
import { type PanelDraft, PanelEditorDialog } from "./PanelEditorDialog";
import { VisibilityLabel } from "./VisibilityLabel";

/** Backend limit on panels per dashboard. */
const MAX_PANELS = 50;

type PendingConfirm = "leave-edit" | "delete" | null;

function newPanelId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `panel-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function panelsEqual(a: readonly DashboardPanelResponse[], b: readonly DashboardPanelResponse[]) {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** A panel as the API stores it, without the script annotations of the response. */
function toPanelModel({
  script_name: _scriptName,
  latest_revision: _latestRevision,
  ...panel
}: DashboardPanelResponse): DashboardPanelModel {
  return panel;
}

function NotFoundState() {
  return (
    <PageContainer maxWidth>
      <ErrorCard
        title="Dashboard not found"
        message="It was deleted, or its owner has not shared it with the project."
      />
      <div className="mt-4 flex justify-center">
        <Link href="/custom-dashboards" className="btn btn-sm">
          <ArrowLeft data-icon="inline-start" aria-hidden="true" />
          All dashboards
        </Link>
      </div>
    </PageContainer>
  );
}

function DashboardSkeleton() {
  return (
    <PageContainer maxWidth>
      <div className="flex flex-col gap-4" aria-busy="true" aria-label="Loading dashboard">
        <div className="skeleton h-8 w-64" />
        <div className="skeleton h-4 w-96 max-w-full" />
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div className="skeleton h-72" />
          <div className="skeleton h-72" />
        </div>
      </div>
    </PageContainer>
  );
}

/** One custom dashboard: its panels on a 12-column grid, with an owner-only edit mode. */
export function CustomDashboardPageContent({ dashboardId }: { dashboardId: string }) {
  const router = useRouter();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { canEdit } = useProject();

  const dashboardQuery = useGetCustomDashboard(dashboardId);
  const dashboard = dashboardQuery.data?.data;
  const updateMutation = useUpdateCustomDashboard();
  const duplicateMutation = useDuplicateCustomDashboard();
  const deleteMutation = useDeleteCustomDashboard();

  // Chip override for this view only; it never changes the stored default.
  const [chipParam, setChipParam] = useQueryState("chip", parseAsString);
  const newestChipId = useDefaultChipId();
  const chipId = chipParam || dashboard?.chip_id || newestChipId;
  const topologyId = useChipTopologyId(chipId);

  const mayEdit = canEdit && !!dashboard?.can_edit;
  const [editing, setEditing] = useState(false);
  // Panels keep the response's script annotations so a draft can show "newer revision" badges.
  const [draft, setDraft] = useState<DashboardPanelResponse[]>([]);
  // The stored version the draft is based on; a panel save is refused (409) once it is stale,
  // and the draft stays so the user can keep or copy their edits.
  const [draftVersion, setDraftVersion] = useState<number | null>(null);
  const [editorPanelId, setEditorPanelId] = useState<string | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [pendingConfirm, setPendingConfirm] = useState<PendingConfirm>(null);

  const savedPanels = useMemo(() => dashboard?.panels ?? [], [dashboard?.panels]);
  const panels = editing ? draft : savedPanels;
  const orderedPanels = useMemo(() => sortPanels(panels), [panels]);
  const dirty = editing && !panelsEqual(draft, savedPanels);

  // Warn before a reload or tab close drops unsaved layout changes.
  useEffect(() => {
    if (!dirty) return;
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault();
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [dirty]);

  // Leave edit mode when the caller loses edit rights, e.g. after a role change.
  useEffect(() => {
    if (editing && dashboard && !mayEdit) setEditing(false);
  }, [dashboard, editing, mayEdit]);

  const storeResponse = (response: CustomDashboardResponse) => {
    queryClient.setQueryData(getGetCustomDashboardQueryKey(dashboardId), (current: unknown) =>
      current && typeof current === "object" ? { ...current, data: response } : current,
    );
    void queryClient.invalidateQueries({ queryKey: getGetCustomDashboardQueryKey(dashboardId) });
    void queryClient.invalidateQueries({ queryKey: getListCustomDashboardsQueryKey() });
  };

  const update = (
    data: CustomDashboardUpdateRequest,
    {
      success,
      failure,
      onDone,
    }: { success: string; failure: string; onDone?: (response: CustomDashboardResponse) => void },
  ) => {
    updateMutation.mutate(
      { dashboardId, data },
      {
        onSuccess: (response) => {
          storeResponse(response.data);
          toast.success(success);
          onDone?.(response.data);
        },
        onError: (error) => toast.error(getApiErrorMessage(error, failure)),
      },
    );
  };

  const startEditing = () => {
    setDraft(savedPanels);
    setDraftVersion(dashboard?.version ?? null);
    setEditing(true);
  };

  const stopEditing = () => {
    if (dirty) {
      setPendingConfirm("leave-edit");
      return;
    }
    setEditing(false);
  };

  const savePanels = () => {
    const submitted = draft;
    update(
      {
        panels: submitted.map(toPanelModel),
        ...(draftVersion !== null ? { expected_version: draftVersion } : {}),
      },
      {
        success: "Dashboard saved",
        failure: "Failed to save the dashboard",
        // Adopt the server's copy so the draft matches what was stored, unless
        // the user kept editing while the request was in flight.
        onDone: (response) => {
          setDraftVersion(response.version);
          setDraft((current) => (current === submitted ? response.panels : current));
        },
      },
    );
  };

  const handleCopyLink = async () => {
    try {
      await copyText(window.location.href);
      toast.success("Link copied");
    } catch {
      toast.error("Failed to copy the link");
    }
  };

  const handleDuplicate = () => {
    duplicateMutation.mutate(
      { dashboardId },
      {
        onSuccess: (response) => {
          void queryClient.invalidateQueries({ queryKey: getListCustomDashboardsQueryKey() });
          toast.success(`Duplicated as "${response.data.name}"`);
          router.push(`/custom-dashboards/${response.data.dashboard_id}`);
        },
        onError: (error) =>
          toast.error(getApiErrorMessage(error, "Failed to duplicate the dashboard")),
      },
    );
  };

  const handleDelete = () => {
    deleteMutation.mutate(
      { dashboardId },
      {
        onSuccess: () => {
          void queryClient.invalidateQueries({ queryKey: getListCustomDashboardsQueryKey() });
          setPendingConfirm(null);
          toast.success("Dashboard deleted");
          router.push("/custom-dashboards");
        },
        onError: (error) => {
          setPendingConfirm(null);
          toast.error(getApiErrorMessage(error, "Failed to delete the dashboard"));
        },
      },
    );
  };

  const handleSettings = (values: DashboardFormValues) => {
    setSettingsError(null);
    updateMutation.mutate(
      { dashboardId, data: values },
      {
        onSuccess: (response) => {
          storeResponse(response.data);
          // A settings save directly on top of the draft's base leaves its panels current.
          setDraftVersion((base) =>
            base !== null && response.data.version === base + 1 ? response.data.version : base,
          );
          setSettingsOpen(false);
          toast.success("Settings saved");
        },
        onError: (error) =>
          setSettingsError(getApiErrorMessage(error, "Failed to save the settings")),
      },
    );
  };

  const handlePanelCommand = (panelId: string, command: PanelCommand) => {
    if (command === "edit") {
      setEditorPanelId(panelId);
      setEditorOpen(true);
      return;
    }
    setDraft((current) => {
      const panel = current.find((entry) => entry.panel_id === panelId);
      if (!panel) return current;
      if (command === "remove") return current.filter((entry) => entry.panel_id !== panelId);
      if (command === "update-revision") {
        const latest = panel.latest_revision;
        if (panel.type !== "metric_script" || !latest) return current;
        return current.map((entry) =>
          entry.panel_id === panelId
            ? { ...entry, config: { ...entry.config, script_revision: latest } }
            : entry,
        );
      }
      if (command === "duplicate") {
        if (current.length >= MAX_PANELS) return current;
        const below = nextPanelLayout(current, panel.type);
        const copy: DashboardPanelResponse = {
          ...panel,
          panel_id: newPanelId(),
          title: panel.title ? `${panel.title} (copy)` : "",
          layout: { ...panel.layout, y: below.y },
          config: structuredClone(panel.config ?? {}),
        };
        return [...current, copy];
      }
      const moved = current.map((entry) =>
        entry.panel_id === panelId
          ? { ...entry, layout: applyLayoutAction(entry.layout, command) }
          : entry,
      );
      return resolveCollisions(moved, panelId);
    });
  };

  const handleEditorSave = (panelDraft: PanelDraft) => {
    setDraft((current) => {
      if (editorPanelId) {
        return current.map((entry) =>
          entry.panel_id === editorPanelId ? { ...entry, ...panelDraft } : entry,
        );
      }
      return [
        ...current,
        {
          panel_id: newPanelId(),
          ...panelDraft,
          layout: nextPanelLayout(current, panelDraft.type),
        },
      ];
    });
    setEditorOpen(false);
  };

  if (dashboardQuery.isLoading) return <DashboardSkeleton />;
  if (isAxiosError(dashboardQuery.error) && dashboardQuery.error.response?.status === 404) {
    return <NotFoundState />;
  }
  if (dashboardQuery.isError || !dashboard) {
    return (
      <PageContainer maxWidth>
        <ErrorCard
          title="Failed to load the dashboard"
          message={getApiErrorMessage(dashboardQuery.error, "The dashboard could not be loaded")}
          onRetry={() => void dashboardQuery.refetch()}
          retrying={dashboardQuery.isRefetching}
        />
      </PageContainer>
    );
  }

  const shared = dashboard.visibility === "project";
  const editorPanel = editorPanelId
    ? (draft.find((entry) => entry.panel_id === editorPanelId) ?? null)
    : null;
  const busy = updateMutation.isPending;

  const toggleSharing = () =>
    update(
      { visibility: shared ? "private" : "project" },
      {
        success: shared ? "Dashboard is now private" : "Dashboard shared with the project",
        failure: "Failed to change sharing",
      },
    );

  // Copy link and Duplicate stay visible for everyone they apply to; the owner-only
  // sharing, settings and delete actions sit behind one overflow menu next to Edit.
  const viewActions = (
    <>
      <button type="button" className="btn btn-ghost btn-sm" onClick={handleCopyLink}>
        <LinkIcon data-icon="inline-start" aria-hidden="true" />
        Copy link
      </button>
      {canEdit && (
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={handleDuplicate}
          disabled={duplicateMutation.isPending}
        >
          {duplicateMutation.isPending ? (
            <span data-icon="inline-start" className="loading loading-spinner loading-xs" />
          ) : (
            <Copy data-icon="inline-start" aria-hidden="true" />
          )}
          Duplicate
        </button>
      )}
      {mayEdit && !editing && (
        <button type="button" className="btn btn-primary btn-sm" onClick={startEditing}>
          <Pencil data-icon="inline-start" aria-hidden="true" />
          Edit
        </button>
      )}
      {mayEdit && (
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <button
              type="button"
              className="btn btn-ghost btn-sm btn-square"
              aria-label="Dashboard actions"
            >
              <EllipsisVertical className="h-4 w-4" aria-hidden="true" />
            </button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem disabled={busy} onSelect={toggleSharing}>
              {shared ? (
                <Lock className="h-4 w-4" aria-hidden="true" />
              ) : (
                <Users className="h-4 w-4" aria-hidden="true" />
              )}
              {shared ? "Make private" : "Share with project"}
            </DropdownMenuItem>
            <DropdownMenuItem
              onSelect={() => {
                setSettingsError(null);
                setSettingsOpen(true);
              }}
            >
              <Settings className="h-4 w-4" aria-hidden="true" />
              Dashboard settings
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              className="text-error data-[highlighted]:text-error"
              onSelect={() => setPendingConfirm("delete")}
            >
              <Trash2 className="h-4 w-4" aria-hidden="true" />
              Delete dashboard
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      )}
    </>
  );

  return (
    <PageContainer maxWidth>
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between sm:gap-4">
        <div className="flex min-w-0 items-start gap-2">
          <Link
            href="/custom-dashboards"
            className="btn btn-ghost btn-sm btn-square shrink-0"
            aria-label="All dashboards"
          >
            <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          </Link>
          <div className="min-w-0">
            <h1 className="truncate text-xl font-medium">{dashboard.name}</h1>
            {dashboard.description && (
              <p className="mt-1 text-sm text-base-content/70">{dashboard.description}</p>
            )}
            <p className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-base-content/60">
              <VisibilityLabel visibility={dashboard.visibility} />
              <span>by {dashboard.owner_username}</span>
              <span title={formatDateTime(dashboard.updated_at)}>
                Updated {formatRelativeTime(dashboard.updated_at)}
              </span>
              {dashboard.chip_id && (
                <span>
                  Default chip <span className="font-mono">{dashboard.chip_id}</span>
                </span>
              )}
            </p>
          </div>
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2 sm:justify-end">
          {viewActions}
        </div>
      </div>

      <div className="mb-4 flex items-center gap-3">
        <label htmlFor="custom-dashboard-chip" className="text-xs text-base-content/60">
          Chip
        </label>
        <div className="w-full sm:w-72">
          <ChipSelector
            inputId="custom-dashboard-chip"
            selectedChip={chipId}
            onChipSelect={(next) =>
              void setChipParam(next && next !== dashboard.chip_id ? next : null)
            }
          />
        </div>
      </div>

      {editing && (
        <div
          role="toolbar"
          aria-label="Edit dashboard"
          className="sticky top-0 z-20 mb-4 flex flex-wrap items-center gap-2 rounded-[var(--radius-box)] border border-base-content/10 bg-base-100 p-2"
        >
          <span className="px-1 text-sm font-medium">Editing</span>
          {dirty ? (
            <span className="inline-flex items-center gap-1 text-xs text-warning">
              <CircleAlert className="h-3.5 w-3.5" aria-hidden="true" />
              Unsaved changes
            </span>
          ) : (
            <span className="text-xs text-base-content/60">No unsaved changes</span>
          )}
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <button
              type="button"
              className="btn btn-sm"
              disabled={draft.length >= MAX_PANELS}
              title={draft.length >= MAX_PANELS ? `At most ${MAX_PANELS} panels` : undefined}
              onClick={() => {
                setEditorPanelId(null);
                setEditorOpen(true);
              }}
            >
              <Plus data-icon="inline-start" aria-hidden="true" />
              Add panel
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={!dirty || busy}
              onClick={() => setDraft(savedPanels)}
            >
              <RotateCcw data-icon="inline-start" aria-hidden="true" />
              Discard
            </button>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={!dirty || busy}
              onClick={savePanels}
            >
              {busy ? (
                <span data-icon="inline-start" className="loading loading-spinner loading-xs" />
              ) : (
                <Save data-icon="inline-start" aria-hidden="true" />
              )}
              Save
            </button>
            <button type="button" className="btn btn-ghost btn-sm" onClick={stopEditing}>
              Done
            </button>
          </div>
        </div>
      )}

      {orderedPanels.length === 0 ? (
        <EmptyState
          emoji="chart"
          title="This dashboard has no panels"
          description={
            mayEdit
              ? "Add metric heatmaps, metric script results or Markdown notes"
              : "Its owner has not added any panels yet"
          }
          action={
            mayEdit ? (
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => {
                  if (!editing) startEditing();
                  setEditorPanelId(null);
                  setEditorOpen(true);
                }}
              >
                <Plus data-icon="inline-start" aria-hidden="true" />
                Add panel
              </button>
            ) : undefined
          }
        />
      ) : (
        <div
          className="grid grid-cols-1 gap-4 md:auto-rows-[120px] md:grid-cols-12"
          data-testid="custom-dashboard-grid"
        >
          {orderedPanels.map((panel) => (
            <DashboardPanelCard
              key={panel.panel_id}
              panel={panel}
              chipId={chipId}
              topologyId={topologyId}
              editing={editing}
              onCommand={handlePanelCommand}
            />
          ))}
        </div>
      )}

      {mayEdit && (
        <>
          <PanelEditorDialog
            open={editorOpen}
            panel={editorPanel}
            dashboardShared={shared}
            onOpenChange={setEditorOpen}
            onSave={handleEditorSave}
          />
          <DashboardFormDialog
            open={settingsOpen}
            mode="edit"
            initial={{
              name: dashboard.name,
              description: dashboard.description,
              visibility: dashboard.visibility,
              chip_id: dashboard.chip_id,
            }}
            pending={busy}
            error={settingsError}
            onOpenChange={setSettingsOpen}
            onSubmit={handleSettings}
          />
        </>
      )}

      <ConfirmDialog
        open={pendingConfirm === "leave-edit"}
        title="Discard unsaved changes"
        description="Your panel changes have not been saved. Leave edit mode and discard them?"
        confirmLabel="Discard changes"
        destructive
        onOpenChange={(open) => !open && setPendingConfirm(null)}
        onConfirm={() => {
          setPendingConfirm(null);
          setDraft(savedPanels);
          setEditing(false);
        }}
      />
      <ConfirmDialog
        open={pendingConfirm === "delete"}
        title="Delete dashboard"
        description={`Delete "${dashboard.name}"? Project members it is shared with lose access too.`}
        confirmLabel="Delete"
        destructive
        pending={deleteMutation.isPending}
        onOpenChange={(open) => !open && setPendingConfirm(null)}
        onConfirm={handleDelete}
      />
    </PageContainer>
  );
}
