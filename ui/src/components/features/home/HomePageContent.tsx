"use client";

import Link from "next/link";
import { useMemo, useState } from "react";
import {
  ArrowRight,
  CalendarClock,
  CheckCircle2,
  ClipboardList,
  Gauge,
  GraduationCap,
  Play,
  Workflow,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import type { FlowScheduleSummary } from "@/schemas";

import { useListChips } from "@/client/chip/chip";
import { useListAllFlowSchedules } from "@/client/flow/flow";
import { useListTaskResults } from "@/client/task-result/task-result";
import { FirstCalibrationHomeCard } from "@/components/features/first-calibration/FirstCalibrationHomeCard";
import { useFirstCalibrationJourney } from "@/components/features/first-calibration/useFirstCalibrationJourney";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { useProject } from "@/contexts/ProjectContext";
import { formatDateTime, formatRelativeFutureTime, formatRelativeTime } from "@/lib/utils/datetime";
import { selectUpcomingRuns } from "@/lib/utils/flowSchedules";
import { QubitTile } from "@/components/ui/QubitTile";

import { HOME_ACTIVITY_DAYS, HomeExecutionActivity } from "./HomeExecutionActivity";

interface SectionHeadingProps {
  id?: string;
  title: string;
  description: string;
  href?: string;
  linkLabel?: string;
}

interface QuickActionsProps {
  canEdit: boolean;
}

interface UpcomingRunsProps {
  canEdit: boolean;
}

interface QuickAction {
  href: string;
  label: string;
  description: string;
  icon: LucideIcon;
}

function SectionHeading({ id, title, description, href, linkLabel }: SectionHeadingProps) {
  return (
    <div className="flex flex-col items-start justify-between gap-2 sm:flex-row sm:gap-4">
      <div>
        <h2 id={id} className="text-sm font-medium">
          {title}
        </h2>
        <p className="mt-0.5 text-sm text-base-content/60">{description}</p>
      </div>
      {/* Offset the ghost padding when stacked so the label lines up with the heading. */}
      {href && linkLabel && (
        <Link href={href} className="btn btn-ghost btn-sm -ml-3 shrink-0 gap-1 sm:ml-0">
          {linkLabel}
          <ArrowRight className="h-4 w-4" />
        </Link>
      )}
    </div>
  );
}

function QuickActions({ canEdit }: QuickActionsProps) {
  const actions: QuickAction[] = [
    ...(canEdit
      ? [
          {
            href: "/tasks",
            label: "Run a task",
            description: "Start a calibration task",
            icon: Play,
          },
          {
            href: "/workflow",
            label: "Open workflows",
            description: "Create or run a workflow",
            icon: Workflow,
          },
        ]
      : []),
    {
      href: "/dashboard",
      label: "View dashboard",
      description: "Check overall chip health",
      icon: Gauge,
    },
    {
      href: "/task-results",
      label: "Find task results",
      description: "Investigate recent outcomes",
      icon: ClipboardList,
    },
  ];

  return (
    <section aria-labelledby="quick-actions-heading">
      <h2 id="quick-actions-heading" className="mb-3 text-sm font-medium text-base-content/60">
        Quick actions
      </h2>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {actions.map(({ href, label, description, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className="card card-interactive border border-base-300 bg-base-100 shadow-sm"
          >
            <div className="card-body flex-row items-center gap-3 p-4">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-base-200 text-base-content/70">
                <Icon className="h-5 w-5" />
              </span>
              <span className="min-w-0">
                <span className="block font-medium">{label}</span>
                <span className="block text-xs text-base-content/55">{description}</span>
              </span>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}

const UPCOMING_RUN_LIMIT = 5;

function UpcomingRunRow({ run, canEdit }: { run: FlowScheduleSummary; canEdit: boolean }) {
  const content = (
    <>
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-base-200 text-base-content/60">
        <CalendarClock className="h-4 w-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-medium">{run.flow_name}</span>
        <span className="mt-1 flex flex-wrap items-center gap-2 text-xs text-base-content/55">
          {run.chip_id && <span className="badge badge-ghost badge-sm">{run.chip_id}</span>}
          <time dateTime={run.next_run ?? undefined} className="tabular-nums">
            {formatDateTime(run.next_run, "yyyy-MM-dd HH:mm")}
          </time>
        </span>
      </span>
      <span className="shrink-0 text-xs text-base-content/60 tabular-nums">
        {formatRelativeFutureTime(run.next_run)}
      </span>
    </>
  );

  return (
    <li className="py-3 first:pt-0 last:pb-0">
      {canEdit ? (
        <Link
          href={`/workflow/${encodeURIComponent(run.flow_name)}`}
          className="flex items-center gap-3 hover:text-primary"
        >
          {content}
        </Link>
      ) : (
        <div className="flex items-center gap-3">{content}</div>
      )}
    </li>
  );
}

function UpcomingRuns({ canEdit }: UpcomingRunsProps) {
  const { data, isLoading, error } = useListAllFlowSchedules(undefined, {
    query: { staleTime: 30_000, refetchInterval: 60_000 },
  });
  const upcomingRuns = useMemo(
    () => selectUpcomingRuns(data?.data.schedules ?? [], UPCOMING_RUN_LIMIT),
    [data],
  );

  return (
    <section className="card bg-base-200 shadow-sm">
      <div className="card-body gap-4 p-5">
        <SectionHeading
          title="Upcoming runs"
          description="The next scheduled workflow runs in this project"
          href={canEdit ? "/workflow" : undefined}
          linkLabel={canEdit ? "All workflows" : undefined}
        />
        {isLoading ? (
          <div className="space-y-2">
            <div className="skeleton h-12 w-full" />
            <div className="skeleton h-12 w-full" />
          </div>
        ) : error ? (
          <div role="alert" className="alert alert-error py-3 text-sm">
            Failed to load scheduled runs.
          </div>
        ) : upcomingRuns.length === 0 ? (
          <div className="flex items-center gap-3 rounded-lg bg-base-100/60 p-4">
            <CalendarClock className="h-6 w-6 shrink-0 text-base-content/40" />
            <p className="text-sm text-base-content/60">No upcoming scheduled runs.</p>
          </div>
        ) : (
          <ul aria-label="Upcoming runs" className="divide-y divide-base-300">
            {upcomingRuns.map((run) => (
              <UpcomingRunRow key={run.schedule_id} run={run} canEdit={canEdit} />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

export function HomePageContent() {
  const { canEdit } = useProject();
  const journey = useFirstCalibrationJourney();
  const [journeyStartRequested, setJourneyStartRequested] = useState(false);
  const {
    data: chipsResponse,
    isLoading: chipsLoading,
    error: chipsError,
  } = useListChips({ query: { staleTime: 30_000 } });
  const {
    data: failedResponse,
    isLoading: failedLoading,
    error: failedError,
  } = useListTaskResults(
    { status: "failed", limit: 5 },
    { query: { staleTime: 15_000, refetchInterval: 60_000 } },
  );

  const failedResults = failedResponse?.data.items ?? [];
  const chips = chipsResponse?.data.chips ?? [];
  const showJourney = canEdit && !chipsLoading && !chipsError;
  const showJourneyStart =
    showJourney && chips.length > 0 && !journey.state && !journeyStartRequested;

  return (
    <PageContainer maxWidth>
      <PageHeader
        title="Home"
        description="Recent execution activity and what needs attention"
        actions={
          showJourneyStart && (
            <button
              type="button"
              className="btn btn-ghost btn-sm gap-2"
              onClick={() => setJourneyStartRequested(true)}
            >
              <GraduationCap size={18} aria-hidden="true" />
              First calibration guide
            </button>
          )
        }
      />

      <div className="space-y-6">
        {showJourney && (
          <FirstCalibrationHomeCard
            projectHasChips={chips.length > 0}
            startRequested={journeyStartRequested}
            onStartDismissed={() => setJourneyStartRequested(false)}
          />
        )}

        <QuickActions canEdit={canEdit} />

        <section
          aria-labelledby="home-execution-activity-heading"
          className="card bg-base-200 shadow-sm"
        >
          <div className="card-body gap-4 p-5">
            <SectionHeading
              id="home-execution-activity-heading"
              title="Executions"
              description={`Calibration runs across this project over the last ${HOME_ACTIVITY_DAYS} days`}
              href="/execution"
              linkLabel="All executions"
            />
            <HomeExecutionActivity />
          </div>
        </section>

        <UpcomingRuns canEdit={canEdit} />

        <section className="card bg-base-200 shadow-sm">
          <div className="card-body gap-4 p-5">
            <SectionHeading
              title="Needs attention"
              description="Recent failed task results to investigate"
              href="/task-results?status=failed"
              linkLabel="View failures"
            />
            {failedLoading ? (
              <div className="space-y-2">
                <div className="skeleton h-16 w-full" />
                <div className="skeleton h-16 w-full" />
              </div>
            ) : failedError ? (
              <div className="alert alert-error py-3 text-sm">Failed to load task results.</div>
            ) : failedResults.length === 0 ? (
              <div className="flex items-center gap-3 rounded-lg bg-base-100/60 p-4">
                <CheckCircle2 className="h-6 w-6 shrink-0 text-success" />
                <div>
                  <p className="font-medium">No failed task results</p>
                  <p className="text-sm text-base-content/55">
                    There is nothing waiting for investigation.
                  </p>
                </div>
              </div>
            ) : (
              <div className="divide-y divide-base-300">
                {failedResults.map((result) => (
                  <Link
                    key={result.task_id}
                    href={`/task-results/${encodeURIComponent(result.task_id)}`}
                    className="flex items-center gap-3 py-3 first:pt-0 last:pb-0 hover:text-error"
                  >
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-sm font-medium">{result.task_name}</span>
                      <span className="mt-1 flex items-center gap-2 text-xs text-base-content/55">
                        <QubitTile qid={result.qid} status="failed" />
                        <span className="shrink-0">{result.chip_id}</span>
                        {result.message && <span className="truncate">{result.message}</span>}
                      </span>
                    </span>
                    {result.start_at && (
                      <span className="hidden shrink-0 text-xs text-base-content/50 sm:block">
                        {formatRelativeTime(result.start_at)}
                      </span>
                    )}
                  </Link>
                ))}
              </div>
            )}
          </div>
        </section>
      </div>
    </PageContainer>
  );
}
