"use client";

import { useId } from "react";

import { CheckCircle2, CircleAlert } from "lucide-react";

import type { ListConfigSourcesResponse } from "@/schemas";

interface HardwareReadinessCheckProps {
  chipId: string;
  configSources: ListConfigSourcesResponse | undefined;
  confirmed: boolean;
  onConfirmedChange: (confirmed: boolean) => void;
}

function CheckRow({ ok, label }: { ok: boolean | null; label: string }) {
  return (
    <li className="flex items-start gap-2">
      {ok ? (
        <CheckCircle2 size={16} className="mt-0.5 shrink-0 text-success" aria-hidden="true" />
      ) : (
        <CircleAlert size={16} className="mt-0.5 shrink-0 text-warning" aria-hidden="true" />
      )}
      <span className="min-w-0 break-words">
        {label}
        <span className="sr-only">{ok ? " (found)" : " (not found)"}</span>
      </span>
    </li>
  );
}

/**
 * What QDash can check before a first run on real hardware, and the confirmation it cannot make
 * itself. A scaffolded configuration only holds placeholders, so the user confirms that the wiring
 * and parameters match the connected device.
 */
export function HardwareReadinessCheck({
  chipId,
  configSources,
  confirmed,
  onConfirmedChange,
}: HardwareReadinessCheckProps) {
  const checkboxId = useId();
  const treeAvailable = configSources?.available ?? null;
  const wiringFound = configSources
    ? configSources.sources.some((source) => source.system_id === chipId)
    : null;

  return (
    <div className="space-y-2 text-sm">
      <p className="text-xs font-medium text-base-content/60">Hardware readiness</p>
      <ul className="space-y-1">
        <CheckRow
          ok={treeAvailable}
          label={
            treeAvailable
              ? "Configuration directory is mounted"
              : "Configuration directory is not mounted on this deployment"
          }
        />
        <CheckRow
          ok={wiringFound}
          label={
            wiringFound
              ? `Wiring file for ${chipId} found`
              : `No wiring file for ${chipId} in the configuration directory`
          }
        />
      </ul>
      <div className="flex items-start gap-2">
        <input
          id={checkboxId}
          type="checkbox"
          className="checkbox checkbox-sm mt-0.5"
          checked={confirmed}
          onChange={(event) => onConfirmedChange(event.target.checked)}
        />
        <label htmlFor={checkboxId} className="min-w-0 cursor-pointer break-words">
          Wiring and device parameters of {chipId} match the connected hardware
        </label>
      </div>
    </div>
  );
}
