"use client";

import Link from "next/link";
import {
  ArrowRight,
  CheckCircle2,
  ClipboardList,
  Cpu,
  Gauge,
  GraduationCap,
  MessageSquare,
  Play,
  Workflow,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { useListChips } from "@/client/chip/chip";
import { useListTaskResults } from "@/client/task-result/task-result";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { useProject } from "@/contexts/ProjectContext";
import { useNotificationActions, useNotifications } from "@/hooks/useNotifications";
import { formatRelativeTime } from "@/lib/utils/datetime";
import type { NotificationResponse } from "@/schemas";
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

function RecentNotifications() {
  const { data, isLoading, error } = useNotifications(false);
  const { markRead } = useNotificationActions();
  const notifications = (data?.data.notifications ?? []).slice(0, 5);

  const handleOpen = (notification: NotificationResponse) => {
    if (notification.read_at == null) {
      markRead.mutate({ notificationId: notification.id });
    }
  };

  return (
    <section className="card bg-base-200 shadow-sm">
      <div className="card-body gap-4 p-5">
        <SectionHeading
          title="Recent notifications"
          description="Mentions and replies from your project"
          href="/inbox"
          linkLabel="View inbox"
        />
        {isLoading ? (
          <div className="flex justify-center py-10">
            <span className="loading loading-spinner loading-md" />
          </div>
        ) : error ? (
          <div className="alert alert-error py-3 text-sm">Failed to load notifications.</div>
        ) : notifications.length === 0 ? (
          <EmptyState
            title="You are all caught up"
            description="New mentions and replies will appear here."
            emoji="check"
            size="sm"
            className="rounded-lg bg-base-100/60 px-4"
          />
        ) : (
          <div className="divide-y divide-base-300">
            {notifications.map((notification) => (
              <Link
                key={notification.id}
                href={notification.target_url}
                onClick={() => handleOpen(notification)}
                className="flex gap-3 py-3 first:pt-0 last:pb-0 hover:text-primary"
              >
                <span
                  className={`mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${
                    notification.read_at == null
                      ? "bg-primary text-primary-content"
                      : "bg-base-200 text-base-content/55"
                  }`}
                >
                  <MessageSquare className="h-4 w-4" />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="line-clamp-1 block text-sm font-medium">
                    {notification.title}
                  </span>
                  {notification.excerpt && (
                    <span className="mt-0.5 line-clamp-1 block text-xs text-base-content/55">
                      {notification.excerpt}
                    </span>
                  )}
                  <span className="mt-1 block text-xs text-base-content/50">
                    {notification.actor_username} · {formatRelativeTime(notification.created_at)}
                  </span>
                </span>
              </Link>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

export function HomePageContent() {
  const { canEdit } = useProject();
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
  const hasChips = (chipsResponse?.data.chips.length ?? 0) > 0;
  const showGettingStarted = canEdit && !chipsLoading && !chipsError && !hasChips;
  const showHeaderTour = canEdit && !chipsLoading && (hasChips || Boolean(chipsError));

  return (
    <PageContainer maxWidth>
      <PageHeader
        title="Home"
        description="Recent execution activity and what needs attention"
        actions={
          showHeaderTour && (
            <Link href="/chip?tutorial=create-chip" className="btn btn-ghost btn-sm gap-2">
              <GraduationCap size={18} />
              Setup tour
            </Link>
          )
        }
      />

      <div className="space-y-6">
        {showGettingStarted && (
          <section className="flex flex-col gap-4 rounded-xl border border-primary/25 bg-primary/5 p-4 sm:flex-row sm:items-center sm:justify-between sm:p-5">
            <div className="flex items-start gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-base-200 text-base-content/70">
                <Cpu size={20} />
              </span>
              <div>
                <h2 className="font-medium">Create your first chip</h2>
                <p className="mt-1 text-sm text-base-content/60">
                  Set up the device QDash will use for calibration tasks and results.
                </p>
              </div>
            </div>
            <Link
              href="/chip?tutorial=create-chip"
              className="btn btn-primary btn-sm shrink-0 gap-2 sm:self-center"
            >
              <GraduationCap size={18} />
              Start setup tour
            </Link>
          </section>
        )}

        <QuickActions canEdit={canEdit} />

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
          <div className="space-y-6">
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
                          <span className="block truncate text-sm font-medium">
                            {result.task_name}
                          </span>
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

          <RecentNotifications />
        </div>
      </div>
    </PageContainer>
  );
}
