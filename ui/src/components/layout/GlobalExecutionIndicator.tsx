"use client";

import { useEffect, useRef } from "react";
import { useRouter } from "next/navigation";

import { Activity, ExternalLink } from "lucide-react";

import { useGetExecutionLockStatus } from "@/client/execution/execution";
import { useToast } from "@/components/ui/Toast";

const ACTIVE_STATUSES = new Set(["scheduled", "pending", "running"]);
const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);

interface ExecutionStatusSnapshot {
  executionId: string;
  status: string;
}

export function GlobalExecutionIndicator() {
  const router = useRouter();
  const toast = useToast();
  const previousStatus = useRef<ExecutionStatusSnapshot | null>(null);
  const initialized = useRef(false);
  const { data } = useGetExecutionLockStatus({
    query: {
      refetchInterval: 2000,
      refetchIntervalInBackground: true,
    },
  });
  const lockStatus = data?.data;
  const executionId = lockStatus?.execution_id ?? "";
  const chipId = lockStatus?.chip_id ?? "";
  const status = lockStatus?.status ?? "";
  const hasActiveMetadata = Boolean(executionId && ACTIVE_STATUSES.has(status));
  const executionHref =
    executionId && chipId
      ? `/execution/${encodeURIComponent(chipId)}/${encodeURIComponent(executionId)}`
      : "";

  useEffect(() => {
    if (!executionId || !status) return;
    const current = { executionId, status };
    if (!initialized.current) {
      initialized.current = true;
      previousStatus.current = current;
      return;
    }

    const previous = previousStatus.current;
    if (
      previous?.executionId === executionId &&
      ACTIVE_STATUSES.has(previous.status) &&
      TERMINAL_STATUSES.has(status)
    ) {
      const message = lockStatus?.name || "Calibration execution";
      const options = executionHref
        ? {
            action: {
              label: "View",
              onClick: () => router.push(executionHref),
            },
          }
        : undefined;
      if (status === "completed") toast.success(`${message} completed`, options);
      else if (status === "failed") toast.error(`${message} failed`, options);
      else toast.info(`${message} was cancelled`, options);
    }
    previousStatus.current = current;
  }, [executionHref, executionId, lockStatus?.name, router, status, toast]);

  if (!lockStatus?.lock) return null;

  const label = hasActiveMetadata ? lockStatus.name || "Calibration" : "Calibration starting";
  const content = (
    <>
      <span className="loading loading-spinner loading-xs" aria-hidden="true" />
      <span className="hidden max-w-48 truncate sm:inline">{label}</span>
      <span className="text-xs opacity-60">Running</span>
      {executionHref && hasActiveMetadata && <ExternalLink size={13} aria-hidden="true" />}
    </>
  );

  if (!executionHref || !hasActiveMetadata) {
    return (
      <div className="badge badge-info h-8 gap-2 px-3" role="status" aria-live="polite">
        <Activity size={14} aria-hidden="true" />
        {content}
      </div>
    );
  }

  return (
    <button
      type="button"
      className="badge badge-info h-8 gap-2 px-3 transition-opacity hover:opacity-80"
      onClick={() => router.push(executionHref)}
      title={`Open ${label} execution`}
    >
      {content}
    </button>
  );
}
