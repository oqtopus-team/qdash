"use client";

import Link from "next/link";

import { useQuery } from "@tanstack/react-query";
import { CalendarClock, Clock, ExternalLink } from "lucide-react";

import type { FlowScheduleSummary } from "@/schemas";

import { listAllFlowSchedules } from "@/client/flow/flow";
import { EmptyState } from "@/components/ui/EmptyState";
import { formatDateTime } from "@/lib/utils/datetime";

function formatScheduleType(schedule: FlowScheduleSummary) {
  return schedule.schedule_type === "cron" ? "Recurring" : "One-time";
}

function getNextRunLabel(schedule: FlowScheduleSummary) {
  if (schedule.schedule_type === "cron") {
    return schedule.cron || "Cron schedule";
  }
  return schedule.next_run ? formatDateTime(schedule.next_run) : "Scheduled";
}

function ScheduleRow({ schedule }: { schedule: FlowScheduleSummary }) {
  const isCron = schedule.schedule_type === "cron";

  return (
    <Link
      href={`/workflow/${schedule.flow_name}`}
      className="group block rounded-lg border border-base-300 bg-base-100 p-3 transition-colors hover:border-primary/50"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate font-semibold">{schedule.flow_name}</div>
          <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-base-content/60">
            <span>{formatScheduleType(schedule)}</span>
            <span className={`badge badge-xs ${schedule.active ? "badge-success" : "badge-ghost"}`}>
              {schedule.active ? "Active" : "Inactive"}
            </span>
          </div>
        </div>
        <ExternalLink className="h-3.5 w-3.5 shrink-0 text-base-content/35 transition-colors group-hover:text-primary" />
      </div>
      <div className="mt-3 grid gap-1.5 text-xs text-base-content/70">
        <div className="flex min-w-0 items-center gap-2">
          <Clock className="h-3.5 w-3.5 shrink-0 text-base-content/40" />
          <span className={isCron ? "font-mono" : ""}>{getNextRunLabel(schedule)}</span>
        </div>
        <div className="flex min-w-0 items-center gap-2">
          <CalendarClock className="h-3.5 w-3.5 shrink-0 text-base-content/40" />
          <span>Created {formatDateTime(schedule.created_at)}</span>
        </div>
      </div>
    </Link>
  );
}

function SectionShell({
  children,
  headerActions,
}: {
  children: React.ReactNode;
  headerActions?: React.ReactNode;
}) {
  return (
    <div className="card bg-base-200 shadow-lg">
      <div className="card-body">
        <div className="flex flex-wrap items-start justify-between gap-x-3 gap-y-2">
          <h2 className="card-title">Schedule Status</h2>
          {headerActions}
        </div>
        {children}
      </div>
    </div>
  );
}

export function FlowSchedulesSection() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["flow-schedules"],
    queryFn: () => listAllFlowSchedules(),
    refetchInterval: 10000,
  });

  if (isLoading) {
    return (
      <SectionShell>
        <div className="flex justify-center py-8">
          <span className="loading loading-spinner loading-md"></span>
        </div>
      </SectionShell>
    );
  }

  if (error) {
    return (
      <SectionShell>
        <div className="alert alert-error mt-2">
          <span>Failed to load schedules: {(error as Error)?.message}</span>
        </div>
      </SectionShell>
    );
  }

  const schedules = data?.data?.schedules || [];

  if (schedules.length === 0) {
    return (
      <SectionShell>
        <EmptyState
          title="No schedules configured"
          description="Schedule a flow run to see it here."
          emoji="hourglass"
          size="sm"
        />
      </SectionShell>
    );
  }

  const activeCount = schedules.filter((schedule) => schedule.active).length;
  const recurringCount = schedules.filter((schedule) => schedule.schedule_type === "cron").length;

  const sortedSchedules = [...schedules].sort((a, b) => {
    const aTime = a.next_run ? new Date(a.next_run).getTime() : Number.MAX_SAFE_INTEGER;
    const bTime = b.next_run ? new Date(b.next_run).getTime() : Number.MAX_SAFE_INTEGER;
    if (aTime !== bTime) return aTime - bTime;
    return a.flow_name.localeCompare(b.flow_name);
  });

  return (
    <SectionShell
      headerActions={
        <div className="flex flex-wrap gap-1.5">
          <span className="badge badge-outline badge-sm">{recurringCount} cron</span>
          <span className="badge badge-outline badge-sm">
            {schedules.length - recurringCount} one-time
          </span>
        </div>
      }
    >
      <p className="text-xs text-base-content/60">
        {activeCount} active of {schedules.length} schedules
      </p>

      <div className="mt-2 space-y-2">
        {sortedSchedules.slice(0, 12).map((schedule) => (
          <ScheduleRow key={schedule.schedule_id} schedule={schedule} />
        ))}
      </div>

      {sortedSchedules.length > 12 && (
        <div className="mt-3 text-xs text-base-content/60">
          Showing 12 of {sortedSchedules.length} schedules
        </div>
      )}
    </SectionShell>
  );
}
