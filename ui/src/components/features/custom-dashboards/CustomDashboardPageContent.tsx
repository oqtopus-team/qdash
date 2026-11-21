"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { useQueryClient } from "@tanstack/react-query";
import { isAxiosError } from "axios";
import {
  ArrowLeft,
  Bot,
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
  useCreateCustomDashboard,
  useDeleteCustomDashboard,
  useDuplicateCustomDashboard,
  useGetCustomDashboard,
  useListCustomDashboardTemplates,
  usePreviewCustomDashboardTemplate,
  useUpdateCustomDashboard,
} from "@/client/custom-dashboard/custom-dashboard";
import { useListMetricScripts } from "@/client/metric-script/metric-script";
import type {
  CustomDashboardResponse,
  CustomDashboardUpdateRequest,
  DashboardPanelResponse,
} from "@/schemas";
import { ChipSelector } from "@/components/selectors/ChipSelector";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
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
import { useOptionalChatDock } from "@/contexts/ChatDockContext";
import { useProject } from "@/contexts/ProjectContext";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import { copyText } from "@/lib/utils/clipboard";
import { formatDateTime, formatRelativeTime } from "@/lib/utils/datetime";
import {
  useChipTopologyId,
  useDefaultChipId,
} from "@/components/features/metric-scripts/useChipTopology";

import {
  dashboardSuggestions,
  EMPTY_NEW_DASHBOARD,
  MAX_PANELS,
  NEW_DASHBOARD_PATH,
  type NewDashboardMeta,
  parseDashboardDraft,
  serializeDashboardDraft,
  toPanelModel,
} from "./dashboardDraft";
import { DashboardFormDialog, type DashboardFormValues } from "./DashboardFormDialog";
import { DashboardPanelCard, type PanelCommand } from "./DashboardPanelCard";
import { applyLayoutAction, nextPanelLayout, resolveCollisions, sortPanels } from "./layout";
import { type PanelDraft, PanelEditorDialog } from "./PanelEditorDialog";
import { readMetricScriptConfig } from "./panelConfig";
import { VisibilityLabel } from "./VisibilityLabel";

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

/**
 * One custom dashboard: its panels on a 12-column grid, with an owner-only edit mode. With
 * no `dashboardId` it is a new dashboard that exists only as a local draft until Save
 * creates it. The draft is shared with the Agent panel, which can propose a new draft; the
 * user applies a proposal to the draft and saves it here.
 */
export function CustomDashboardPageContent({ dashboardId }: { dashboardId: string | null }) {
  const router = useRouter();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { canEdit } = useProject();
  const dock = useOptionalChatDock();
  const isNew = dashboardId === null;
  // Mutations of the stored dashboard run only once it exists.
  const storedId = dashboardId ?? "";

  const dashboardQuery = useGetCustomDashboard(dashboardId ?? "", {
    query: { enabled: !isNew },
  });
  const dashboard = isNew ? undefined : dashboardQuery.data?.data;
  const updateMutation = useUpdateCustomDashboard();
  const createMutation = useCreateCustomDashboard();
  const duplicateMutation = useDuplicateCustomDashboard();
  const deleteMutation = useDeleteCustomDashboard();
  const templatesQuery = useListCustomDashboardTemplates({
    query: { enabled: isNew && canEdit, staleTime: Infinity },
  });

  // A new dashboard's name, description, default chip and starter template.
  const [newMeta, setNewMeta] = useState<NewDashboardMeta>(EMPTY_NEW_DASHBOARD);
  // Set once Save created the dashboard, so leaving for it does not warn.
  const [created, setCreated] = useState(false);
  const [nameMissing, setNameMissing] = useState(false);

  // Chip override for this view only; it never changes the stored default. A new
  // dashboard's chip is its default chip, saved with it.
  const [chipParam, setChipParam] = useQueryState("chip", parseAsString);
  const newestChipId = useDefaultChipId();
  const chipId = isNew
    ? newMeta.chip_id || newestChipId
    : chipParam || dashboard?.chip_id || newestChipId;
  const topologyId = useChipTopologyId(chipId);

  const mayEdit = canEdit && (isNew || !!dashboard?.can_edit);
  const [editing, setEditing] = useState(isNew);
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
  // Why the dashboard cannot be shared yet: the server's reason, or null when the private
  // scripts below explain it on their own.
  const [sharingBlocked, setSharingBlocked] = useState<{ message: string | null } | null>(null);

  // Scripts the caller can see, to explain sharing limits before the server refuses a save.
  const scriptsQuery = useListMetricScripts({ query: { enabled: canEdit } });
  const scripts = useMemo(() => scriptsQuery.data?.data.scripts ?? [], [scriptsQuery.data]);

  const savedPanels = useMemo(() => dashboard?.panels ?? [], [dashboard?.panels]);
  const panels = editing ? draft : savedPanels;
  const orderedPanels = useMemo(() => sortPanels(panels), [panels]);
  const dirty = isNew
    ? !created &&
      (draft.length > 0 || JSON.stringify(newMeta) !== JSON.stringify(EMPTY_NEW_DASHBOARD))
    : editing && !panelsEqual(draft, savedPanels);
  const templates = templatesQuery.data?.data?.templates;
  const pendingTemplate =
    isNew && draft.length === 0 && newMeta.template_id
      ? (templates?.find((entry) => entry.template_id === newMeta.template_id) ?? {
          template_id: newMeta.template_id,
          name: newMeta.template_id,
          panel_count: null,
        })
      : null;
  // What Save would copy in from the starter template, read without writing anything, so the
  // proposed panels can be reviewed before the dashboard exists.
  const templatePreviewQuery = usePreviewCustomDashboardTemplate(
    pendingTemplate?.template_id ?? "",
    { query: { enabled: pendingTemplate !== null, staleTime: 60_000, retry: false } },
  );
  const templatePreview = pendingTemplate ? templatePreviewQuery.data?.data : undefined;
  const starterScripts = useMemo(
    () =>
      new Map(
        (templatePreview?.scripts_to_create ?? []).map((script) => [script.template_id, script]),
      ),
    [templatePreview],
  );
  const previewPanels = useMemo(() => sortPanels(templatePreview?.panels ?? []), [templatePreview]);

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
    queryClient.setQueryData(getGetCustomDashboardQueryKey(storedId), (current: unknown) =>
      current && typeof current === "object" ? { ...current, data: response } : current,
    );
    void queryClient.invalidateQueries({ queryKey: getGetCustomDashboardQueryKey(storedId) });
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
      { dashboardId: storedId, data },
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

  /** Replace the draft with one the Agent proposed and the user applied; never saves. */
  const applyDraft = (code: string): boolean => {
    if (!mayEdit || (!isNew && !dashboard)) return false;
    const parsed = parseDashboardDraft(code, isNew, editing ? draft : savedPanels);
    if (!parsed.ok) {
      toast.error(parsed.problem);
      return false;
    }
    if (!editing) {
      setDraftVersion(dashboard?.version ?? null);
      setEditing(true);
    }
    setDraft(parsed.panels);
    if (parsed.meta) {
      setNewMeta(parsed.meta);
      if (parsed.meta.name.trim()) setNameMissing(false);
    }
    return true;
  };

  // What the Agent panel reads when a turn is sent: the draft as JSON, for a dashboard the
  // user may save. Read-only viewers share only the route and title.
  const pageState = useRef({
    isNew,
    dashboardId,
    dashboard,
    mayEdit,
    editing,
    draft,
    savedPanels,
    newMeta,
    draftVersion,
    chipId,
    dirty,
    applyDraft,
  });
  useEffect(() => {
    pageState.current = {
      isNew,
      dashboardId,
      dashboard,
      mayEdit,
      editing,
      draft,
      savedPanels,
      newMeta,
      draftVersion,
      chipId,
      dirty,
      applyDraft,
    };
    dock?.refreshPage();
  });
  const registerPage = dock?.registerPage;
  useEffect(() => {
    if (!registerPage) return;
    return registerPage({
      current: () => {
        const state = pageState.current;
        const name = state.isNew ? state.newMeta.name : (state.dashboard?.name ?? "");
        const path = state.isNew ? NEW_DASHBOARD_PATH : `/custom-dashboards/${state.dashboardId}`;
        const title = state.isNew ? "New dashboard" : `Dashboard: ${name || state.dashboardId}`;
        const ready = state.mayEdit && (state.isNew || Boolean(state.dashboard));
        if (!ready) return { path, title };
        const panels = state.editing ? state.draft : state.savedPanels;
        return {
          path,
          title,
          dashboard: {
            ...(state.dashboard ? { dashboardId: state.dashboard.dashboard_id } : {}),
            name,
            description: state.isNew ? state.newMeta.description : state.dashboard?.description,
            visibility: state.dashboard?.visibility ?? "private",
            chipId: state.chipId ?? null,
            version: state.editing ? state.draftVersion : (state.dashboard?.version ?? null),
            code: serializeDashboardDraft(panels, state.isNew ? state.newMeta : null),
            dirty: state.dirty,
          },
        };
      },
      applyCode: (code) => pageState.current.applyDraft(code),
      suggestions: () => {
        const state = pageState.current;
        if (!state.mayEdit) return [];
        const panels = state.editing ? state.draft : state.savedPanels;
        return dashboardSuggestions(state.isNew, panels.length === 0);
      },
    });
  }, [registerPage]);

  // Open the Agent panel on this page. Nothing is sent until the user asks.
  const openAgent = dock ? () => dock.openGeneralChat() : null;

  const createDashboard = () => {
    const name = newMeta.name.trim();
    if (!name) {
      setNameMissing(true);
      return;
    }
    createMutation.mutate(
      {
        data: {
          name,
          description: newMeta.description.trim(),
          // A new dashboard is private; sharing is an explicit action after it exists.
          visibility: "private",
          chip_id: chipId || null,
          panels: draft.map(toPanelModel),
          ...(draft.length === 0 && newMeta.template_id
            ? { template_id: newMeta.template_id }
            : {}),
        },
      },
      {
        onSuccess: (response) => {
          setCreated(true);
          void queryClient.invalidateQueries({ queryKey: getListCustomDashboardsQueryKey() });
          toast.success("Dashboard created");
          router.replace(`/custom-dashboards/${response.data.dashboard_id}`);
        },
        // The draft stays so the user can fix what QDash refused.
        onError: (error) =>
          toast.error(getApiErrorMessage(error, "Failed to create the dashboard")),
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
      { dashboardId: storedId },
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
      { dashboardId: storedId },
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
      { dashboardId: storedId, data: values },
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

  if (isNew && !canEdit) {
    return (
      <PageContainer maxWidth>
        <ErrorCard
          title="You cannot create dashboards"
          message="Your role in this project can view dashboards but not create them."
        />
      </PageContainer>
    );
  }
  if (!isNew && dashboardQuery.isLoading) return <DashboardSkeleton />;
  if (
    !isNew &&
    isAxiosError(dashboardQuery.error) &&
    dashboardQuery.error.response?.status === 404
  ) {
    return <NotFoundState />;
  }
  if (!isNew && (dashboardQuery.isError || !dashboard)) {
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

  const shared = dashboard?.visibility === "project";
  const editorPanel = editorPanelId
    ? (draft.find((entry) => entry.panel_id === editorPanelId) ?? null)
    : null;
  const busy = updateMutation.isPending || createMutation.isPending;

  // Private scripts the saved panels use; a shared dashboard may only show shared scripts.
  // Sharing is never granted here: the owner shares the script from its own settings.
  const privateScripts = scripts.filter(
    (script) =>
      script.visibility === "private" &&
      savedPanels.some(
        (panel) =>
          panel.type === "metric_script" &&
          readMetricScriptConfig(panel).script_id === script.script_id,
      ),
  );

  const toggleSharing = () => {
    if (!dashboard) return;
    if (!shared && privateScripts.length > 0) {
      setSharingBlocked({ message: null });
      return;
    }
    updateMutation.mutate(
      { dashboardId: storedId, data: { visibility: shared ? "private" : "project" } },
      {
        onSuccess: (response) => {
          storeResponse(response.data);
          toast.success(shared ? "Dashboard is now private" : "Dashboard shared with the project");
        },
        onError: (error) => {
          if (!shared && isAxiosError(error) && error.response?.status === 422) {
            setSharingBlocked({ message: getApiErrorMessage(error, "Failed to change sharing") });
            return;
          }
          toast.error(getApiErrorMessage(error, "Failed to change sharing"));
        },
      },
    );
  };

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
      {mayEdit && openAgent && (
        <button type="button" className="btn btn-ghost btn-sm" onClick={openAgent}>
          <Bot data-icon="inline-start" aria-hidden="true" />
          Edit with AI
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
          {dashboard ? (
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
          ) : (
            <div className="min-w-0 flex-1">
              <h1 className="sr-only">New dashboard</h1>
              <input
                className={`input input-sm w-full text-base font-medium sm:w-80 ${
                  nameMissing ? "input-error" : ""
                }`}
                aria-label="Dashboard name"
                aria-invalid={nameMissing || undefined}
                aria-describedby={nameMissing ? "new-dashboard-name-error" : undefined}
                placeholder="Untitled dashboard"
                maxLength={200}
                value={newMeta.name}
                onChange={(event) => {
                  const name = event.target.value;
                  setNewMeta((current) => ({ ...current, name }));
                  if (name.trim()) setNameMissing(false);
                }}
              />
              {nameMissing && (
                <p id="new-dashboard-name-error" className="mt-1 text-xs text-error">
                  Name the dashboard before saving
                </p>
              )}
              {newMeta.description && (
                <p className="mt-1 text-sm text-base-content/70">{newMeta.description}</p>
              )}
              <p className="mt-1 text-xs text-base-content/60">
                Draft, not saved yet. It is created private when you save.
              </p>
            </div>
          )}
        </div>
        <div className="flex shrink-0 flex-wrap items-center gap-2 sm:justify-end">
          {dashboard
            ? viewActions
            : openAgent && (
                <button type="button" className="btn btn-sm" onClick={openAgent}>
                  <Bot data-icon="inline-start" aria-hidden="true" />
                  Ask AI
                </button>
              )}
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
            onChipSelect={(next) => {
              if (isNew) setNewMeta((current) => ({ ...current, chip_id: next || null }));
              else void setChipParam(next && next !== dashboard?.chip_id ? next : null);
            }}
          />
        </div>
      </div>

      {editing && (
        <div
          role="toolbar"
          aria-label="Edit dashboard"
          className="sticky top-0 z-20 mb-4 flex flex-wrap items-center gap-2 rounded-[var(--radius-box)] border border-base-content/10 bg-base-100 p-2"
        >
          <span className="px-1 text-sm font-medium">{isNew ? "New dashboard" : "Editing"}</span>
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
              onClick={() => {
                setDraft(savedPanels);
                if (isNew) {
                  setNewMeta(EMPTY_NEW_DASHBOARD);
                  setNameMissing(false);
                }
              }}
            >
              <RotateCcw data-icon="inline-start" aria-hidden="true" />
              Discard
            </button>
            <button
              type="button"
              className="btn btn-primary btn-sm"
              disabled={!dirty || busy}
              onClick={isNew ? createDashboard : savePanels}
            >
              {busy ? (
                <span data-icon="inline-start" className="loading loading-spinner loading-xs" />
              ) : (
                <Save data-icon="inline-start" aria-hidden="true" />
              )}
              Save
            </button>
            {!isNew && (
              <button type="button" className="btn btn-ghost btn-sm" onClick={stopEditing}>
                Done
              </button>
            )}
          </div>
        </div>
      )}

      {pendingTemplate ? (
        <div className="flex flex-col gap-4">
          <div role="status" className="alert alert-soft text-sm">
            <span>
              Preview of the <span className="font-medium">{pendingTemplate.name}</span> template
              {pendingTemplate.panel_count !== null
                ? ` (${pendingTemplate.panel_count} panels)`
                : ""}
              . Nothing is created until you save; Save copies these panels into a private
              dashboard.
              {(templatePreview?.scripts_to_create ?? []).map((script) => (
                <span key={script.template_id}>
                  {" "}
                  Save also adds the metric script{" "}
                  <span className="font-medium">{script.name}</span>, shared with the project, which
                  the script panels read; until then they run its starter source as an unsaved
                  preview.
                </span>
              ))}
            </span>
          </div>
          {templatePreviewQuery.isLoading ? (
            <div
              className="grid grid-cols-1 gap-4 md:grid-cols-2"
              aria-busy="true"
              aria-label="Loading the template preview"
            >
              <div className="skeleton h-72" />
              <div className="skeleton h-72" />
            </div>
          ) : templatePreviewQuery.isError ? (
            <div role="alert" className="alert alert-warning alert-soft text-sm">
              {getApiErrorMessage(
                templatePreviewQuery.error,
                "Failed to load the template preview",
              )}
            </div>
          ) : (
            <div
              className="grid grid-cols-1 gap-4 md:auto-rows-[120px] md:grid-cols-12"
              data-testid="template-preview-grid"
            >
              {previewPanels.map((panel) => {
                const starter = panel.script_template_id
                  ? starterScripts.get(panel.script_template_id)
                  : undefined;
                return (
                  <DashboardPanelCard
                    key={panel.panel_id}
                    panel={panel}
                    chipId={chipId}
                    topologyId={topologyId}
                    editing={false}
                    onCommand={() => {}}
                    starterScript={starter}
                  />
                );
              })}
            </div>
          )}
        </div>
      ) : orderedPanels.length === 0 ? (
        <EmptyState
          emoji="chart"
          title={isNew ? "Describe the dashboard you need" : "This dashboard has no panels"}
          description={
            !mayEdit
              ? "Its owner has not added any panels yet"
              : openAgent
                ? "Ask the Agent for maps, tables or notes. You review its draft here before saving."
                : "Add metric heatmaps, metric script results or Markdown notes"
          }
          action={
            mayEdit ? (
              <div className="flex flex-wrap justify-center gap-2">
                {openAgent && (
                  <button type="button" className="btn btn-primary btn-sm" onClick={openAgent}>
                    <Bot data-icon="inline-start" aria-hidden="true" />
                    Ask AI
                  </button>
                )}
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
              </div>
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
        </>
      )}
      {mayEdit && dashboard && (
        <>
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
      <Dialog
        open={sharingBlocked !== null}
        onOpenChange={(open) => !open && setSharingBlocked(null)}
      >
        <DialogContent className="max-w-lg">
          <DialogTitle>Share with project</DialogTitle>
          <DialogDescription className="mt-1 text-xs text-base-content/60">
            A shared dashboard can only show scripts that are shared with the project
          </DialogDescription>
          <div className="mt-3 flex flex-col gap-3 text-sm">
            {sharingBlocked?.message && (
              <div role="alert" className="alert alert-warning alert-soft text-sm">
                {sharingBlocked.message}
              </div>
            )}
            {privateScripts.length > 0 && (
              <>
                <p>
                  These scripts are private. Share each one first, or replace its panels, then share
                  the dashboard. Nothing is shared on your behalf.
                </p>
                <ul className="divide-y divide-base-content/10 rounded-[var(--radius-box)] border border-base-content/10">
                  {privateScripts.map((script) => (
                    <li
                      key={script.script_id}
                      className="flex flex-wrap items-center justify-between gap-2 px-3 py-2"
                    >
                      <span className="min-w-0">
                        <span className="block truncate font-medium">{script.name}</span>
                        <span className="block text-xs text-base-content/60">
                          by {script.owner_username}
                        </span>
                      </span>
                      {script.can_edit ? (
                        <Link
                          href={`/custom-dashboards/scripts/${script.script_id}#metric-script-settings`}
                          className="btn btn-sm"
                        >
                          Open script settings
                        </Link>
                      ) : (
                        <span className="text-xs text-base-content/60">
                          Ask {script.owner_username} to share it
                        </span>
                      )}
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
          <div className="modal-action mt-2">
            <button type="button" className="btn" onClick={() => setSharingBlocked(null)}>
              Close
            </button>
          </div>
        </DialogContent>
      </Dialog>
      <ConfirmDialog
        open={pendingConfirm === "delete"}
        title="Delete dashboard"
        description={`Delete "${dashboard?.name ?? ""}"? Project members it is shared with lose access too.`}
        confirmLabel="Delete"
        destructive
        pending={deleteMutation.isPending}
        onOpenChange={(open) => !open && setPendingConfirm(null)}
        onConfirm={handleDelete}
      />
    </PageContainer>
  );
}
