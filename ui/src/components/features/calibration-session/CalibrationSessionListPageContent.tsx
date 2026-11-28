"use client";

import Link from "next/link";

import { X } from "lucide-react";
import { useQueryState } from "nuqs";

import type {
  CalibrationSessionOrigin,
  CalibrationSessionStatus,
  ListCalibrationSessionsParams,
} from "@/schemas";

import {
  getListCalibrationSessionsQueryKey,
  useListCalibrationSessions,
} from "@/client/calibration-session/calibration-session";
import {
  projectRequest,
  useLinkedProject,
} from "@/components/features/agent-session/useLinkedProject";
import { ExecutionViewSwitch } from "@/components/features/execution/ExecutionAreaNav";
import { ExecutionActor } from "@/components/features/execution/ExecutionAttribution";
import {
  CalibrationSessionStatusBadge,
  calibrationSessionBorderStyle,
} from "@/components/features/execution/CalibrationSessionStatus";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageFiltersBar } from "@/components/ui/PageFiltersBar";
import { PageHeader } from "@/components/ui/PageHeader";
import {
  SESSION_ORIGIN_FILTERS as ORIGIN_FILTERS,
  SESSION_STATUS_FILTERS as STATUS_FILTERS,
  type SessionReturnContext,
  calibrationSessionDetailHref,
  sessionListParsers,
} from "@/lib/executionArea";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import { formatDateTime } from "@/lib/utils/datetime";

const PAGE_SIZE = 20;
const STATUS_LABELS: Record<(typeof STATUS_FILTERS)[number], string> = {
  all: "All",
  open: "Open",
  closed: "Closed",
};
const ORIGIN_LABELS: Record<(typeof ORIGIN_FILTERS)[number], string> = {
  all: "All origins",
  manual: "Created for an objective",
  automatic: "Automatic",
};

const DESCRIPTION = "Runs and agent sessions grouped by objective";

/**
 * The project's calibration sessions, newest first: one row per objective, linked to its page.
 * It is the Execution area's view by objective, next to the list of every execution.
 *
 * A run started without a session gets an automatic one, so the origin filter separates the
 * sessions people or agents created for an objective from those QDash created for single runs.
 * This page starts nothing.
 */
export function CalibrationSessionListPageContent() {
  const linked = useLinkedProject();
  const projectId = linked.status === "ready" ? linked.projectId : null;
  const [statusFilter, setStatusFilter] = useQueryState("status", sessionListParsers.status);
  const [originFilter, setOriginFilter] = useQueryState("origin", sessionListParsers.origin);
  const [mine, setMine] = useQueryState("mine", sessionListParsers.mine);
  const [chip, setChip] = useQueryState("chip", sessionListParsers.chip);
  const [page, setPage] = useQueryState("page", sessionListParsers.page);
  const currentPage = Math.max(1, page);
  // A session page opened from this list links back to it with the same filters and page.
  const sessionReturn: SessionReturnContext = {
    from: "sessions",
    list: { status: statusFilter, origin: originFilter, mine, chip, page: currentPage },
  };

  const params: ListCalibrationSessionsParams = {
    limit: PAGE_SIZE,
    skip: (currentPage - 1) * PAGE_SIZE,
    ...(statusFilter !== "all" ? { status: [statusFilter as CalibrationSessionStatus] } : {}),
    ...(originFilter !== "all" ? { origin: [originFilter as CalibrationSessionOrigin] } : {}),
    ...(mine ? { mine: true } : {}),
    ...(chip ? { chip_id: chip } : {}),
  };
  const list = useListCalibrationSessions(params, {
    query: {
      queryKey: [...getListCalibrationSessionsQueryKey(params), projectId],
      enabled: projectId !== null,
    },
    request: {
      ...(projectId ? projectRequest(projectId) : {}),
      paramsSerializer: { indexes: null },
    },
  });
  const items = list.data?.data.items ?? [];
  const hasMore = list.data?.data.has_more ?? false;

  const resetPage = () => void setPage(null);

  if (linked.status === "unavailable" || linked.status === "no_project") {
    return (
      <PageContainer>
        <PageHeader title="Execution" description={DESCRIPTION} />
        <ExecutionViewSwitch current="sessions" chipId={chip} className="mb-4" />
        <div role="alert" className="alert alert-error alert-soft">
          <span>
            {linked.status === "unavailable"
              ? `These calibration sessions belong to project ${linked.projectId}, which your account cannot open. Ask a project owner for access.`
              : "Your account has no project, so no calibration session can be listed."}
          </span>
        </div>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <PageHeader title="Execution" description={DESCRIPTION} />
      <ExecutionViewSwitch
        current="sessions"
        chipId={chip}
        projectId={projectId}
        className="mb-4"
      />
      <PageFiltersBar className="mb-4 sm:mb-6">
        <PageFiltersBar.Group className="sm:items-center">
          <PageFiltersBar.Item>
            <div role="tablist" aria-label="Status" className="tabs tabs-box tabs-sm w-fit">
              {STATUS_FILTERS.map((value) => (
                <button
                  key={value}
                  type="button"
                  role="tab"
                  aria-selected={statusFilter === value}
                  className={`tab ${statusFilter === value ? "tab-active" : ""}`}
                  onClick={() => {
                    void setStatusFilter(value === "all" ? null : value);
                    resetPage();
                  }}
                >
                  {STATUS_LABELS[value]}
                </button>
              ))}
            </div>
          </PageFiltersBar.Item>
          <PageFiltersBar.Item className="sm:w-56">
            <select
              className="select select-sm w-full"
              aria-label="Origin"
              value={originFilter}
              onChange={(event) => {
                const value = event.target.value as (typeof ORIGIN_FILTERS)[number];
                void setOriginFilter(value === "all" ? null : value);
                resetPage();
              }}
            >
              {ORIGIN_FILTERS.map((value) => (
                <option key={value} value={value}>
                  {ORIGIN_LABELS[value]}
                </option>
              ))}
            </select>
          </PageFiltersBar.Item>
          {chip ? (
            <PageFiltersBar.Item>
              <span className="badge badge-outline gap-1">
                Chip {chip}
                <button
                  type="button"
                  className="btn btn-ghost btn-xs btn-circle"
                  aria-label="Show every chip"
                  onClick={() => {
                    void setChip(null);
                    resetPage();
                  }}
                >
                  <X className="h-3 w-3" aria-hidden="true" />
                </button>
              </span>
            </PageFiltersBar.Item>
          ) : null}
        </PageFiltersBar.Group>
        <PageFiltersBar.Group>
          <PageFiltersBar.Item>
            <label className="choice-field gap-2 text-sm">
              <input
                type="checkbox"
                className="toggle toggle-sm"
                checked={mine}
                onChange={(event) => {
                  void setMine(event.target.checked ? true : null);
                  resetPage();
                }}
              />
              <span>Only mine</span>
            </label>
          </PageFiltersBar.Item>
        </PageFiltersBar.Group>
      </PageFiltersBar>

      <section aria-labelledby="calibration-sessions-heading">
        <h2 id="calibration-sessions-heading" className="mb-3 text-sm font-medium">
          Calibration sessions
        </h2>
        {linked.status === "pending" || list.isLoading ? (
          <div className="grid grid-cols-1 gap-2" aria-busy="true">
            <div className="skeleton h-20 w-full" />
            <div className="skeleton h-20 w-full" />
            <div className="skeleton h-20 w-full" />
          </div>
        ) : list.isError ? (
          <div role="alert" className="alert alert-error alert-soft">
            <span>
              {getApiErrorMessage(list.error, "Calibration sessions could not be loaded")}
            </span>
          </div>
        ) : items.length === 0 ? (
          <EmptyState
            title="No calibration sessions"
            description={
              currentPage > 1
                ? "No more sessions match these filters"
                : "Sessions appear here when a run starts or someone creates one for an objective"
            }
            emoji="empty"
          />
        ) : (
          <ul className="grid grid-cols-1 gap-2">
            {items.map((session) => (
              <li
                key={session.calibration_session_id}
                className={`rounded-box border border-base-200 bg-base-100 p-3 shadow-sm sm:p-4 ${calibrationSessionBorderStyle(session.status)}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <Link
                    href={calibrationSessionDetailHref(
                      session.calibration_session_id,
                      projectId,
                      sessionReturn,
                    )}
                    className="link link-hover line-clamp-2 min-w-0 text-sm font-medium wrap-anywhere"
                  >
                    {session.objective}
                  </Link>
                  <span className="flex shrink-0 items-center gap-1">
                    {session.origin === "automatic" ? (
                      <span
                        className="badge badge-ghost badge-sm"
                        title="QDash created this session for a run started without one"
                      >
                        Automatic
                      </span>
                    ) : null}
                    <CalibrationSessionStatusBadge status={session.status} />
                  </span>
                </div>
                <div className="mt-0.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-sm text-base-content/60 sm:mt-1">
                  <span>{formatDateTime(session.created_at)}</span>
                  <ExecutionActor actor={{ username: session.created_by }} />
                  <span>Chip {session.chip_id}</span>
                </div>
              </li>
            ))}
          </ul>
        )}

        {currentPage > 1 || hasMore ? (
          <nav
            aria-label="Pages"
            className="my-3 flex items-center justify-center gap-2 sm:my-4 sm:gap-4"
          >
            <button
              type="button"
              className="btn btn-outline btn-xs sm:btn-sm"
              disabled={currentPage <= 1}
              onClick={() => void setPage(currentPage - 1 <= 1 ? null : currentPage - 1)}
            >
              Previous
            </button>
            <span className="text-sm">Page {currentPage}</span>
            <button
              type="button"
              className="btn btn-outline btn-xs sm:btn-sm"
              disabled={!hasMore}
              onClick={() => void setPage(currentPage + 1)}
            >
              Next
            </button>
          </nav>
        ) : null}
      </section>
    </PageContainer>
  );
}
