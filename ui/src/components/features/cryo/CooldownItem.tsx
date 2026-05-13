"use client";

import { forwardRef, useEffect, useMemo, useState } from "react";

import { ChevronDown, ChevronRight, Plus, Trash2, X } from "lucide-react";

import {
  useAssignChipToCooldown,
  useDeleteCooldown,
  useUnassignChipFromCooldown,
  useUpdateCooldown,
} from "@/client/cooldown/cooldown";
import { formatDate, toIsoSeconds } from "@/lib/utils/datetime";

import { CooldownWiringSection } from "./CooldownWiringSection";

interface Cooldown {
  cooldown_id: string;
  cryo_id: string;
  description: string;
  started_at: string;
  ended_at?: string | null;
  chip_ids: string[];
  wiring_info?: string;
  wiring_blocks?: Record<string, unknown>[];
}

interface CooldownItemProps {
  cooldown: Cooldown;
  allChips: string[];
  expanded: boolean;
  onToggle: () => void;
  onChange: () => void;
}

function isoToDateInput(iso: string | null | undefined): string {
  if (!iso) return "";
  return formatDate(iso);
}

function dateInputToIso(value: string, endOfDay = false): string | null {
  if (!value) return null;
  const time = endOfDay ? "T23:59:59" : "T12:00:00";
  return toIsoSeconds(`${value}${time.slice(0, 6)}`);
}

function formatDateRange(
  startedAt: string,
  endedAt: string | null | undefined,
): string {
  const start = formatDate(startedAt);
  if (!endedAt) return `${start} → now`;
  return `${start} → ${formatDate(endedAt)}`;
}

export const CooldownItem = forwardRef<HTMLDivElement, CooldownItemProps>(
  function CooldownItem(
    { cooldown, allChips, expanded, onToggle, onChange },
    ref,
  ) {
    const updateMutation = useUpdateCooldown();
    const deleteMutation = useDeleteCooldown();
    const assignMutation = useAssignChipToCooldown();
    const unassignMutation = useUnassignChipFromCooldown();
    const [chipToAdd, setChipToAdd] = useState("");
    const isActive = !cooldown.ended_at;

    // Dates: click-to-edit
    const [editingDates, setEditingDates] = useState(false);
    const [draftStartedAt, setDraftStartedAt] = useState(
      isoToDateInput(cooldown.started_at),
    );
    const [draftEndedAt, setDraftEndedAt] = useState(
      isoToDateInput(cooldown.ended_at),
    );
    useEffect(() => {
      setDraftStartedAt(isoToDateInput(cooldown.started_at));
      setDraftEndedAt(isoToDateInput(cooldown.ended_at));
    }, [cooldown.started_at, cooldown.ended_at, cooldown.cooldown_id]);

    const availableChips = useMemo(
      () => allChips.filter((c) => !cooldown.chip_ids.includes(c)),
      [allChips, cooldown.chip_ids],
    );

    const handleSaveDates = async () => {
      if (!draftStartedAt) return;
      if (draftEndedAt && draftEndedAt < draftStartedAt) return;
      await updateMutation.mutateAsync({
        cooldownId: cooldown.cooldown_id,
        data: {
          started_at: dateInputToIso(draftStartedAt),
          ended_at: draftEndedAt ? dateInputToIso(draftEndedAt, true) : null,
        },
      });
      setEditingDates(false);
      onChange();
    };

    const handleEnd = async (e: React.MouseEvent) => {
      e.stopPropagation();
      if (!confirm(`End cool-down ${cooldown.cooldown_id} now?`)) return;
      await updateMutation.mutateAsync({
        cooldownId: cooldown.cooldown_id,
        data: { ended_at: new Date().toISOString() },
      });
      onChange();
    };

    const handleDelete = async (e: React.MouseEvent) => {
      e.stopPropagation();
      if (!confirm(`Delete cool-down ${cooldown.cooldown_id}?`)) return;
      await deleteMutation.mutateAsync({ cooldownId: cooldown.cooldown_id });
      onChange();
    };

    const handleAssign = async () => {
      if (!chipToAdd) return;
      await assignMutation.mutateAsync({
        cooldownId: cooldown.cooldown_id,
        chipId: chipToAdd,
      });
      setChipToAdd("");
      onChange();
    };

    const handleUnassign = async (chipId: string) => {
      await unassignMutation.mutateAsync({
        cooldownId: cooldown.cooldown_id,
        chipId,
      });
      onChange();
    };

    return (
      <div
        ref={ref}
        className={`rounded-xl border transition-colors ${
          isActive
            ? "border-success/40 bg-success/5"
            : "border-base-300 bg-base-100"
        }`}
      >
        {/* Header row — always visible, clickable to toggle */}
        <button
          type="button"
          onClick={onToggle}
          className="w-full flex items-center gap-2 px-3 py-2 text-left hover:bg-base-200/40 rounded-t-xl"
          aria-expanded={expanded}
        >
          {expanded ? (
            <ChevronDown className="h-4 w-4 flex-shrink-0 text-base-content/50" />
          ) : (
            <ChevronRight className="h-4 w-4 flex-shrink-0 text-base-content/50" />
          )}
          <div className="min-w-0 flex-1 flex items-center gap-2 flex-wrap">
            <span className="font-mono font-semibold text-sm">
              {cooldown.cooldown_id}
            </span>
            <span
              className={`badge badge-xs ${
                isActive ? "badge-success" : "badge-ghost"
              }`}
            >
              {isActive ? "active" : "ended"}
            </span>
            <span className="text-xs text-base-content/60 tabular-nums">
              {formatDateRange(cooldown.started_at, cooldown.ended_at)}
            </span>
            <span className="text-xs text-base-content/50">
              · {cooldown.chip_ids.length} chip
              {cooldown.chip_ids.length !== 1 ? "s" : ""}
            </span>
          </div>
          <div
            className="flex gap-1 flex-shrink-0"
            onClick={(e) => e.stopPropagation()}
          >
            {isActive && (
              <button
                className="btn btn-xs btn-warning"
                onClick={handleEnd}
                disabled={updateMutation.isPending}
                title="End this cool-down (warm-up)"
              >
                End now
              </button>
            )}
            <button
              className="btn btn-xs btn-ghost text-error"
              onClick={handleDelete}
              disabled={deleteMutation.isPending}
              title="Delete this cool-down"
            >
              <Trash2 className="h-3 w-3" />
            </button>
          </div>
        </button>

        {/* Expanded body */}
        {expanded && (
          <div className="px-4 pb-4 pt-1 space-y-4 border-t border-base-300">
            {/* Dates inline edit */}
            <div className="text-xs">
              <div className="text-base-content/60 font-semibold uppercase tracking-wide mb-1">
                Dates
              </div>
              {!editingDates ? (
                <button
                  onClick={() => setEditingDates(true)}
                  className="text-base-content/80 inline-flex items-center gap-1.5 rounded px-1 -ml-1 hover:bg-base-200 transition-colors tabular-nums"
                  title="Edit dates"
                >
                  {formatDateRange(cooldown.started_at, cooldown.ended_at)}
                  {isActive && (
                    <span className="text-success/80 ml-1">· still active</span>
                  )}
                </button>
              ) : (
                <div className="flex flex-wrap items-end gap-2">
                  <label className="flex flex-col">
                    <span className="text-[10px] text-base-content/60 uppercase">
                      Started
                    </span>
                    <input
                      type="date"
                      className="input input-xs input-bordered tabular-nums"
                      value={draftStartedAt}
                      onChange={(e) => setDraftStartedAt(e.target.value)}
                      autoFocus
                    />
                  </label>
                  <label className="flex flex-col">
                    <span className="text-[10px] text-base-content/60 uppercase">
                      Ended (empty = active)
                    </span>
                    <input
                      type="date"
                      className="input input-xs input-bordered tabular-nums"
                      value={draftEndedAt}
                      onChange={(e) => setDraftEndedAt(e.target.value)}
                      min={draftStartedAt}
                    />
                  </label>
                  <button
                    className="btn btn-xs btn-primary"
                    onClick={handleSaveDates}
                    disabled={
                      !draftStartedAt ||
                      (!!draftEndedAt && draftEndedAt < draftStartedAt) ||
                      updateMutation.isPending
                    }
                  >
                    Save
                  </button>
                  <button
                    className="btn btn-xs btn-ghost"
                    onClick={() => {
                      setDraftStartedAt(isoToDateInput(cooldown.started_at));
                      setDraftEndedAt(isoToDateInput(cooldown.ended_at));
                      setEditingDates(false);
                    }}
                  >
                    Cancel
                  </button>
                </div>
              )}
            </div>

            {/* Chip management */}
            <div className="text-xs">
              <div className="text-base-content/60 font-semibold uppercase tracking-wide mb-1">
                Chips loaded
                <span className="text-base-content/40 normal-case font-normal ml-1">
                  ({cooldown.chip_ids.length})
                </span>
              </div>
              <div className="flex flex-wrap gap-1.5 items-center">
                {cooldown.chip_ids.length === 0 && (
                  <span className="text-base-content/40 italic">
                    No chips loaded.
                  </span>
                )}
                {cooldown.chip_ids.map((chipId) => (
                  <span
                    key={chipId}
                    className="badge badge-outline badge-md gap-1 pr-1 font-mono"
                  >
                    {chipId}
                    <button
                      className="hover:text-error"
                      onClick={() => handleUnassign(chipId)}
                      disabled={unassignMutation.isPending}
                      title="Unload"
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                ))}
                {availableChips.length > 0 && (
                  <div className="flex items-center gap-1">
                    <select
                      className="select select-xs select-bordered max-w-[10rem]"
                      value={chipToAdd}
                      onChange={(e) => setChipToAdd(e.target.value)}
                    >
                      <option value="">Load chip…</option>
                      {availableChips.map((c) => (
                        <option key={c} value={c}>
                          {c}
                        </option>
                      ))}
                    </select>
                    <button
                      className="btn btn-xs btn-primary"
                      onClick={handleAssign}
                      disabled={!chipToAdd || assignMutation.isPending}
                      title="Load selected chip"
                    >
                      <Plus className="h-3 w-3" />
                    </button>
                  </div>
                )}
              </div>
            </div>

            {/* Wiring info (BlockNote) */}
            <CooldownWiringSection
              cooldownId={cooldown.cooldown_id}
              wiringInfo={cooldown.wiring_info ?? ""}
              wiringBlocks={cooldown.wiring_blocks ?? []}
              onChange={onChange}
            />
          </div>
        )}
      </div>
    );
  },
);
