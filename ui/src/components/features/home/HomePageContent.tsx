"use client";

import Link from "next/link";
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  ClipboardList,
  Gauge,
  MessageSquare,
  Play,
  Workflow,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { useGetExecutionLockStatus } from "@/client/execution/execution";
import { useListTaskResults } from "@/client/task-result/task-result";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageContainer } from "@/components/ui/PageContainer";
import { PageHeader } from "@/components/ui/PageHeader";
import { useProject } from "@/contexts/ProjectContext";
import { useNotificationActions, useNotifications } from "@/hooks/useNotifications";
import { formatRelativeTime } from "@/lib/utils/datetime";
import type { NotificationResponse } from "@/schemas";

const ACTIVE_STATUSES = new Set(["scheduled", "pending", "running"]);

interface SectionHeadingProps {
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

function SectionHeading({ title, description, href, linkLabel }: SectionHeadingProps) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="mt-0.5 text-sm text-base-content/60">{description}</p>
      </div>
      {href && linkLabel && (
        <Link href={href} className="btn btn-ghost btn-sm shrink-0 gap-1">
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
      <h2 id="quick-actions-heading" className="mb-3 text-sm font-semibold text-base-content/60">
        Quick actions
      </h2>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {actions.map(({ href, label, description, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className="card card-interactive border border-base-300 bg-base-100 shadow-sm"
          >
            <div className="card-body flex-row items-center gap-3 p-4">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Icon className="h-5 w-5" />
              </span>
              <span className="min-w-0">
                <span className="block font-semibold">{label}</span>
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
    <section className="card bg-base-200 shadow-lg">
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
  const { data: lockResponse, isLoading: lockLoading } = useGetExecutionLockStatus({
    query: { refetchInterval: 5000, refetchIntervalInBackground: true },
  });
  const {
    data: failedResponse,
    isLoading: failedLoading,
    error: failedError,
  } = useListTaskResults(
    { status: "failed", limit: 5 },
    { query: { staleTime: 15_000, refetchInterval: 60_000 } },
  );

  const lock = lockResponse?.data;
  const isRunning = Boolean(lock?.lock && lock.status && ACTIVE_STATUSES.has(lock.status));
  const executionHref =
    lock?.chip_id && lock.execution_id
      ? `/execution/${encodeURIComponent(lock.chip_id)}/${encodeURIComponent(lock.execution_id)}`
      : "/execution";
  const failedResults = failedResponse?.data.items ?? [];

  return (
    <PageContainer maxWidth>
      <PageHeader title="Home" description="Start work and review what needs your attention" />

      <div className="space-y-6">
        <QuickActions canEdit={canEdit} />

        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
          <div className="space-y-6">
            <section className="card bg-base-200 shadow-lg">
              <div className="card-body gap-4 p-5">
                <SectionHeading
                  title="Current execution"
                  description="The calibration currently running in this project"
                  href="/execution"
                  linkLabel="All executions"
                />
                {lockLoading ? (
                  <div className="skeleton h-24 w-full" />
                ) : isRunning ? (
                  <Link
                    href={executionHref}
                    className="flex items-center gap-4 rounded-lg border border-info/30 bg-info/10 p-4 transition-colors hover:bg-info/15"
                  >
                    <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full bg-info text-info-content">
                      <span className="loading loading-spinner loading-sm" />
                    </span>
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-semibold">
                        {lock?.name || "Calibration execution"}
                      </span>
                      <span className="mt-1 flex flex-wrap gap-x-3 text-xs text-base-content/60">
                        <span className="capitalize">{lock?.status}</span>
                        {lock?.chip_id && <span>Chip {lock.chip_id}</span>}
                      </span>
                    </span>
                    <ArrowRight className="h-5 w-5 shrink-0" />
                  </Link>
                ) : (
                  <div className="flex items-center gap-3 rounded-lg bg-base-100/60 p-4">
                    <CheckCircle2 className="h-6 w-6 shrink-0 text-success" />
                    <div>
                      <p className="font-medium">No calibration is running</p>
                      <p className="text-sm text-base-content/55">
                        This project is ready for the next run.
                      </p>
                    </div>
                  </div>
                )}
              </div>
            </section>

            <section className="card bg-base-200 shadow-lg">
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
                        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-error/10 text-error">
                          <AlertCircle className="h-5 w-5" />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-semibold">
                            {result.task_name}
                          </span>
                          <span className="mt-0.5 block truncate text-xs text-base-content/55">
                            {result.qid} · {result.chip_id}
                            {result.message ? ` · ${result.message}` : ""}
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
