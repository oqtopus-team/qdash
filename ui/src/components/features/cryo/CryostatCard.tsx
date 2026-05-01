"use client";

import { useMemo, useState } from "react";

import {
  Activity,
  ChevronDown,
  ChevronRight,
  Plus,
  Snowflake,
  Trash2,
  X,
} from "lucide-react";

import {
  useAssignChipToCooldown,
  useDeleteCooldown,
  useUnassignChipFromCooldown,
  useUpdateCooldown,
} from "@/client/cooldown/cooldown";
import { useDeleteCryostat } from "@/client/cryostat/cryostat";
import { Card } from "@/components/ui/Card";

interface Cooldown {
  cooldown_id: string;
  cryo_id: string;
  description: string;
  started_at: string;
  ended_at?: string | null;
  chip_ids: string[];
}

interface Cryo {
  cryo_id: string;
  name: string;
  location?: string;
  status?: string;
}

interface CryostatCardProps {
  cryo: Cryo;
  cooldowns: Cooldown[];
  allChips: string[];
  onChange: () => void;
  onCreateCooldown: () => void;
}

const DAY_MS = 24 * 60 * 60 * 1000;

function daysBetween(from: Date, to: Date): number {
  return Math.max(0, Math.floor((to.getTime() - from.getTime()) / DAY_MS));
}

function formatRelativeDays(days: number): string {
  if (days === 0) return "today";
  if (days === 1) return "1 day ago";
  return `${days} days ago`;
}

export function CryostatCard({
  cryo,
  cooldowns,
  allChips,
  onChange,
  onCreateCooldown,
}: CryostatCardProps) {
  const [expanded, setExpanded] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const deleteCryostat = useDeleteCryostat();

  // Sort newest first for timeline rendering and details lookup
  const sortedCooldowns = useMemo(
    () =>
      [...cooldowns].sort(
        (a, b) =>
          new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
      ),
    [cooldowns],
  );

  // Active cool-down (the most recent one with no ended_at)
  const activeCooldown = sortedCooldowns.find((c) => !c.ended_at);

  // Aggregate stats
  const stats = useMemo(() => {
    const now = new Date();
    let totalDaysCooled = 0;
    sortedCooldowns.forEach((cd) => {
      const start = new Date(cd.started_at);
      const end = cd.ended_at ? new Date(cd.ended_at) : now;
      totalDaysCooled += daysBetween(start, end);
    });
    const chipsLoaded = activeCooldown?.chip_ids ?? [];
    return {
      totalCooldowns: sortedCooldowns.length,
      totalDaysCooled,
      chipsLoaded,
    };
  }, [sortedCooldowns, activeCooldown]);

  const selectedCooldown =
    sortedCooldowns.find((c) => c.cooldown_id === selectedId) ??
    activeCooldown ??
    sortedCooldowns[0];

  const handleDelete = async () => {
    if (
      !confirm(
        `Delete cryostat ${cryo.cryo_id}? Existing cool-downs are not affected.`,
      )
    ) {
      return;
    }
    await deleteCryostat.mutateAsync({ cryoId: cryo.cryo_id });
    onChange();
  };

  return (
    <Card variant="default" padding="md">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <button
          className="flex items-center gap-3 text-left flex-1 min-w-0"
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? (
            <ChevronDown className="h-4 w-4 flex-shrink-0" />
          ) : (
            <ChevronRight className="h-4 w-4 flex-shrink-0" />
          )}
          <Snowflake className="h-6 w-6 text-info flex-shrink-0" />
          <div className="min-w-0 flex-1">
            <div className="flex items-baseline gap-2 flex-wrap">
              <span className="font-bold text-lg">{cryo.cryo_id}</span>
              {cryo.name && (
                <span className="text-base-content/70 text-sm truncate">
                  {cryo.name}
                </span>
              )}
              <span
                className={`badge badge-sm ${
                  cryo.status === "active"
                    ? "badge-success"
                    : cryo.status === "maintenance"
                      ? "badge-warning"
                      : "badge-ghost"
                }`}
              >
                {cryo.status ?? "active"}
              </span>
            </div>
            <div className="text-xs text-base-content/60 mt-0.5 flex flex-wrap gap-x-3">
              {cryo.location && <span>📍 {cryo.location}</span>}
              <span>
                {stats.totalCooldowns} cool-down
                {stats.totalCooldowns !== 1 ? "s" : ""}
              </span>
              <span>{stats.totalDaysCooled} days cooled</span>
              <span>
                {stats.chipsLoaded.length} chip
                {stats.chipsLoaded.length !== 1 ? "s" : ""} loaded now
              </span>
            </div>
          </div>
        </button>
        <button
          className="btn btn-ghost btn-xs text-error flex-shrink-0"
          onClick={handleDelete}
          disabled={deleteCryostat.isPending}
          title="Delete cryostat"
        >
          <Trash2 className="h-3 w-3" />
        </button>
      </div>

      {expanded && (
        <div className="mt-4 space-y-4">
          {/* Active cool-down banner */}
          {activeCooldown && (
            <ActiveCooldownBanner
              cooldown={activeCooldown}
              onSelect={() => setSelectedId(activeCooldown.cooldown_id)}
            />
          )}

          {/* Timeline */}
          {sortedCooldowns.length > 0 ? (
            <CooldownTimeline
              cooldowns={sortedCooldowns}
              selectedId={selectedCooldown?.cooldown_id ?? null}
              onSelect={(id) => setSelectedId(id)}
            />
          ) : (
            <div className="text-xs text-base-content/50 italic text-center py-4">
              No cool-downs yet.
            </div>
          )}

          {/* New cool-down trigger */}
          <div className="flex justify-end">
            <button
              className="btn btn-sm btn-primary gap-1"
              onClick={onCreateCooldown}
            >
              <Plus className="h-3.5 w-3.5" />
              New cool-down
            </button>
          </div>

          {/* Detail panel */}
          {selectedCooldown && (
            <CooldownDetail
              cooldown={selectedCooldown}
              allChips={allChips}
              onChange={onChange}
            />
          )}
        </div>
      )}
    </Card>
  );
}

function ActiveCooldownBanner({
  cooldown,
  onSelect,
}: {
  cooldown: Cooldown;
  onSelect: () => void;
}) {
  const start = new Date(cooldown.started_at);
  const days = daysBetween(start, new Date());
  return (
    <button
      onClick={onSelect}
      className="w-full text-left rounded-lg border border-success/40 bg-success/10 px-3 py-2 hover:bg-success/15 transition-colors"
    >
      <div className="flex items-center gap-2 text-sm font-semibold">
        <Activity className="h-4 w-4 text-success" />
        Currently cooling — {cooldown.cooldown_id}
      </div>
      <div className="text-xs text-base-content/70 mt-0.5">
        Started {formatRelativeDays(days)} ({start.toLocaleDateString()}) ·{" "}
        {cooldown.chip_ids.length} chip
        {cooldown.chip_ids.length !== 1 ? "s" : ""} loaded
        {cooldown.chip_ids.length > 0 && `: ${cooldown.chip_ids.join(", ")}`}
      </div>
    </button>
  );
}

function CooldownTimeline({
  cooldowns,
  selectedId,
  onSelect,
}: {
  cooldowns: Cooldown[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  // Bounds: t_min = earliest started_at, t_max = latest ended_at (or now)
  const now = Date.now();
  const tMin = Math.min(
    ...cooldowns.map((c) => new Date(c.started_at).getTime()),
  );
  const tMax = Math.max(
    ...cooldowns.map((c) =>
      c.ended_at ? new Date(c.ended_at).getTime() : now,
    ),
  );
  // Add 5% padding on each side so bars don't touch the edges
  const range = Math.max(1, tMax - tMin);
  const padding = range * 0.05;
  const lo = tMin - padding;
  const hi = tMax + padding;
  const span = hi - lo;

  // Generate ~5 evenly spaced tick labels
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => {
    const t = lo + span * f;
    const date = new Date(t);
    return {
      pct: f * 100,
      label: date.toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
      }),
    };
  });

  return (
    <div>
      <div className="text-xs text-base-content/60 mb-1">Timeline</div>
      <div className="relative h-20 bg-base-200/50 rounded-md border border-base-300">
        {cooldowns.map((cd, i) => {
          const start = new Date(cd.started_at).getTime();
          const end = cd.ended_at ? new Date(cd.ended_at).getTime() : now;
          const left = ((start - lo) / span) * 100;
          const width = Math.max(0.5, ((end - start) / span) * 100);
          const isActive = !cd.ended_at;
          const isSelected = cd.cooldown_id === selectedId;
          // Stack rows: cycle through 3 rows so adjacent bars don't overlap visually
          const row = i % 3;
          const top = 4 + row * 18;
          return (
            <button
              key={cd.cooldown_id}
              onClick={() => onSelect(cd.cooldown_id)}
              className={`absolute rounded transition-all hover:brightness-110 ${
                isActive
                  ? "bg-success/80 hover:bg-success"
                  : "bg-info/60 hover:bg-info/80"
              } ${isSelected ? "ring-2 ring-primary ring-offset-1" : ""}`}
              style={{
                left: `${left}%`,
                width: `${width}%`,
                top: `${top}px`,
                height: "14px",
              }}
              title={`${cd.cooldown_id} (${new Date(cd.started_at).toLocaleDateString()} → ${cd.ended_at ? new Date(cd.ended_at).toLocaleDateString() : "now"})`}
            >
              <span className="text-[9px] font-bold text-white px-1 truncate block leading-[14px]">
                {cd.cooldown_id}
              </span>
            </button>
          );
        })}
      </div>
      {/* Time axis */}
      <div className="relative h-4 mt-1">
        {ticks.map((t, i) => (
          <span
            key={i}
            className="absolute text-[10px] text-base-content/50 -translate-x-1/2"
            style={{ left: `${t.pct}%` }}
          >
            {t.label}
          </span>
        ))}
      </div>
    </div>
  );
}

function isoToDateInput(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toISOString().slice(0, 10);
}

function dateInputToIso(value: string, endOfDay = false): string | null {
  if (!value) return null;
  const time = endOfDay ? "T23:59:59" : "T12:00:00";
  return new Date(`${value}${time}`).toISOString();
}

function CooldownDetail({
  cooldown,
  allChips,
  onChange,
}: {
  cooldown: Cooldown;
  allChips: string[];
  onChange: () => void;
}) {
  const updateMutation = useUpdateCooldown();
  const deleteMutation = useDeleteCooldown();
  const assignMutation = useAssignChipToCooldown();
  const unassignMutation = useUnassignChipFromCooldown();
  const [chipToAdd, setChipToAdd] = useState("");
  const [editingDescription, setEditingDescription] = useState(false);
  const [draftDescription, setDraftDescription] = useState(
    cooldown.description,
  );
  const [editingDates, setEditingDates] = useState(false);
  const [draftStartedAt, setDraftStartedAt] = useState(
    isoToDateInput(cooldown.started_at),
  );
  const [draftEndedAt, setDraftEndedAt] = useState(
    isoToDateInput(cooldown.ended_at),
  );

  const isActive = !cooldown.ended_at;

  const handleEnd = async () => {
    if (!confirm(`End cool-down ${cooldown.cooldown_id} now?`)) return;
    await updateMutation.mutateAsync({
      cooldownId: cooldown.cooldown_id,
      data: { ended_at: new Date().toISOString() },
    });
    onChange();
  };

  const handleDelete = async () => {
    if (!confirm(`Delete cool-down ${cooldown.cooldown_id}?`)) return;
    await deleteMutation.mutateAsync({ cooldownId: cooldown.cooldown_id });
    onChange();
  };

  const handleSaveDescription = async () => {
    await updateMutation.mutateAsync({
      cooldownId: cooldown.cooldown_id,
      data: { description: draftDescription },
    });
    setEditingDescription(false);
    onChange();
  };

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

  const availableChips = allChips.filter((c) => !cooldown.chip_ids.includes(c));

  return (
    <div className="rounded-lg border border-base-300 bg-base-200/40 p-3 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-mono font-bold text-base">
              {cooldown.cooldown_id}
            </span>
            <span
              className={`badge badge-sm ${
                isActive ? "badge-success" : "badge-ghost"
              }`}
            >
              {isActive ? "active" : "ended"}
            </span>
          </div>
          {!editingDates && (
            <div className="text-xs text-base-content/60 mt-0.5">
              Started {new Date(cooldown.started_at).toLocaleString()}
              {cooldown.ended_at && (
                <> · Ended {new Date(cooldown.ended_at).toLocaleString()}</>
              )}
              {!cooldown.ended_at && " · still active"}
              <button
                className="ml-2 link link-primary text-[11px]"
                onClick={() => {
                  setDraftStartedAt(isoToDateInput(cooldown.started_at));
                  setDraftEndedAt(isoToDateInput(cooldown.ended_at));
                  setEditingDates(true);
                }}
              >
                edit dates
              </button>
            </div>
          )}
          {editingDates && (
            <div className="mt-1 flex flex-wrap items-end gap-2 text-xs">
              <label className="flex flex-col">
                <span className="text-[10px] text-base-content/60 uppercase">
                  Started
                </span>
                <input
                  type="date"
                  className="input input-xs input-bordered tabular-nums"
                  value={draftStartedAt}
                  onChange={(e) => setDraftStartedAt(e.target.value)}
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
                onClick={() => setEditingDates(false)}
              >
                Cancel
              </button>
            </div>
          )}
        </div>
        <div className="flex gap-1 flex-shrink-0">
          {isActive && (
            <button
              className="btn btn-xs btn-warning gap-1"
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
      </div>

      {/* Description (inline edit) */}
      <div className="text-xs">
        <div className="flex items-center justify-between mb-1">
          <span className="text-base-content/60 font-semibold uppercase tracking-wide">
            Description
          </span>
          {!editingDescription && (
            <button
              className="btn btn-xs btn-ghost"
              onClick={() => {
                setDraftDescription(cooldown.description);
                setEditingDescription(true);
              }}
            >
              Edit
            </button>
          )}
        </div>
        {editingDescription ? (
          <div className="space-y-1">
            <textarea
              className="textarea textarea-bordered w-full text-xs h-16"
              value={draftDescription}
              onChange={(e) => setDraftDescription(e.target.value)}
            />
            <div className="flex gap-2 justify-end">
              <button
                className="btn btn-xs btn-ghost"
                onClick={() => setEditingDescription(false)}
              >
                Cancel
              </button>
              <button
                className="btn btn-xs btn-primary"
                onClick={handleSaveDescription}
                disabled={updateMutation.isPending}
              >
                Save
              </button>
            </div>
          </div>
        ) : (
          <p className="text-base-content/80 whitespace-pre-wrap">
            {cooldown.description || (
              <span className="italic text-base-content/40">
                No description.
              </span>
            )}
          </p>
        )}
      </div>

      {/* Chip management */}
      <div className="text-xs">
        <div className="text-base-content/60 font-semibold uppercase tracking-wide mb-1">
          Chips loaded
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
              className="badge badge-outline badge-md gap-1 pr-1"
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
              >
                <Plus className="h-3 w-3" />
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
