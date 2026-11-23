"use client";

import Link from "next/link";

import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { parseAsBoolean, parseAsInteger, parseAsStringLiteral, useQueryState } from "nuqs";

import type { CalibrationSessionStatus, ListCalibrationSessionsParams } from "@/schemas";

import {
  getListCalibrationSessionsQueryKey,
  useListCalibrationSessions,
} from "@/client/calibration-session/calibration-session";
import {
  projectRequest,
  useLinkedProject,
} from "@/components/features/agent-session/useLinkedProject";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { calibrationSessionHref } from "@/lib/chatCalibrationSession";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import { formatDateTime } from "@/lib/utils/datetime";

const PAGE_SIZE = 20;
const STATUS_FILTERS = ["all", "open", "closed"] as const;
const STATUS_LABELS: Record<(typeof STATUS_FILTERS)[number], string> = {
  all: "All",
  open: "Open",
  closed: "Closed",
};

/**
 * The project's calibration sessions, newest first: one row per objective, linked to its page.
 *
 * A calibration session is optional. Ordinary executions never need one, so this page only
 * lists the ones people or agents created; it starts nothing.
 */
export function CalibrationSessionListPageContent() {
  const linked = useLinkedProject();
  const projectId = linked.status === "ready" ? linked.projectId : null;
  const [statusFilter, setStatusFilter] = useQueryState(
    "status",
    parseAsStringLiteral(STATUS_FILTERS).withDefault("all"),
  );
  const [mine, setMine] = useQueryState("mine", parseAsBoolean.withDefault(false));
  const [chip, setChip] = useQueryState("chip");
  const [page, setPage] = useQueryState("page", parseAsInteger.withDefault(1));
  const currentPage = Math.max(1, page);

  const params: ListCalibrationSessionsParams = {
    limit: PAGE_SIZE,
    skip: (currentPage - 1) * PAGE_SIZE,
    ...(statusFilter !== "all" ? { status: [statusFilter as CalibrationSessionStatus] } : {}),
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
      <PageContainer maxWidth>
        <PageHeader title="Calibration sessions" />
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
    <PageContainer maxWidth>
      <PageHeader
        title="Calibration sessions"
        description="Objectives that group pipeline runs and agent sessions. Ordinary executions need none."
      />
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
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
        {chip ? (
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
        ) : null}
      </div>

      {linked.status === "pending" || list.isLoading ? (
        <div className="flex flex-col gap-2" aria-busy="true">
          <div className="skeleton h-14 w-full" />
          <div className="skeleton h-14 w-full" />
          <div className="skeleton h-14 w-full" />
        </div>
      ) : list.isError ? (
        <div role="alert" className="alert alert-error alert-soft">
          <span>{getApiErrorMessage(list.error, "Calibration sessions could not be loaded")}</span>
        </div>
      ) : items.length === 0 ? (
        <EmptyState
          title="No calibration sessions"
          description={
            currentPage > 1
              ? "No more sessions match these filters"
              : "A calibration session appears here when someone, or an agent on their behalf, starts work toward an objective with one"
          }
          emoji="empty"
        />
      ) : (
        <ul className="list rounded-box border border-base-200 bg-base-100">
          {items.map((session) => (
            <li key={session.calibration_session_id} className="list-row items-center">
              <span
                className={`badge badge-soft badge-sm ${session.status === "open" ? "badge-info" : "badge-ghost"}`}
              >
                {session.status === "open" ? "Open" : "Closed"}
              </span>
              <div className="min-w-0">
                <Link
                  href={calibrationSessionHref(session.calibration_session_id, projectId)}
                  className="link link-hover line-clamp-2 text-sm font-medium wrap-anywhere"
                >
                  {session.objective}
                </Link>
                <div className="text-xs text-base-content/60">
                  {session.chip_id} · @{session.created_by} · {formatDateTime(session.created_at)}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      {currentPage > 1 || hasMore ? (
        <nav aria-label="Pages" className="mt-4 flex items-center justify-center gap-2">
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            disabled={currentPage <= 1}
            onClick={() => void setPage(currentPage - 1 <= 1 ? null : currentPage - 1)}
          >
            <ChevronLeft data-icon="inline-start" aria-hidden="true" />
            Previous
          </button>
          <span className="text-sm text-base-content/60">Page {currentPage}</span>
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            disabled={!hasMore}
            onClick={() => void setPage(currentPage + 1)}
          >
            Next
            <ChevronRight data-icon="inline-end" aria-hidden="true" />
          </button>
        </nav>
      ) : null}
    </PageContainer>
  );
}
