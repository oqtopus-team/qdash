"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { Plus, Trash2 } from "lucide-react";

import { useDeleteCryostat } from "@/client/cryostat/cryostat";
import { formatDate } from "@/lib/utils/datetime";

import { CooldownItem } from "./CooldownItem";
import { CooldownTimeline } from "./CooldownTimeline";

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

function StatChip({ label, emphasis }: { label: string; emphasis?: boolean }) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] tabular-nums ${
        emphasis
          ? "border-primary/30 bg-primary/10 text-primary"
          : "border-base-300 bg-base-200/50 text-base-content/70"
      }`}
    >
      {label}
    </span>
  );
}

export function CryostatCard({
  cryo,
  cooldowns,
  allChips,
  onChange,
  onCreateCooldown,
}: CryostatCardProps) {
  const deleteCryostat = useDeleteCryostat();

  const sortedCooldowns = useMemo(
    () =>
      [...cooldowns].sort(
        (a, b) => new Date(b.started_at).getTime() - new Date(a.started_at).getTime(),
      ),
    [cooldowns],
  );

  const activeCooldown = sortedCooldowns.find((c) => !c.ended_at);

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

  // Accordion: only one cool-down expanded at a time. Defaults to active,
  // or the most recent one if no active cool-down exists.
  const [expandedId, setExpandedId] = useState<string | null>(() => {
    return activeCooldown?.cooldown_id ?? sortedCooldowns[0]?.cooldown_id ?? null;
  });

  const itemRefs = useRef<Map<string, HTMLDivElement>>(new Map());

  const handleSelectFromTimeline = (id: string) => {
    setExpandedId(id);
    // Wait a tick for the panel to expand before scrolling
    requestAnimationFrame(() => {
      const el = itemRefs.current.get(id);
      el?.scrollIntoView({ behavior: "smooth", block: "nearest" });
    });
  };

  // Keep expansion in sync if the active cool-down changes externally and
  // nothing was previously expanded.
  useEffect(() => {
    if (expandedId === null && activeCooldown) {
      setExpandedId(activeCooldown.cooldown_id);
    }
  }, [activeCooldown, expandedId]);

  const handleDelete = async () => {
    if (!confirm(`Delete cryostat ${cryo.cryo_id}? Existing cool-downs are not affected.`)) {
      return;
    }
    await deleteCryostat.mutateAsync({ cryoId: cryo.cryo_id });
    onChange();
  };

  return (
    <section className="py-3">
      {/* Header */}
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-bold text-xl tracking-tight">{cryo.cryo_id}</span>
            {cryo.name && (
              <span className="text-base-content/70 text-sm truncate">{cryo.name}</span>
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
          <div className="mt-2 flex flex-wrap gap-1.5">
            {cryo.location && <StatChip label={cryo.location} />}
            <StatChip
              label={`${stats.totalCooldowns} cool-down${stats.totalCooldowns !== 1 ? "s" : ""}`}
            />
            <StatChip
              label={`${stats.totalDaysCooled} ${stats.totalDaysCooled === 1 ? "day" : "days"} cooled`}
            />
            <StatChip
              label={`${stats.chipsLoaded.length} chip${stats.chipsLoaded.length !== 1 ? "s" : ""} now`}
              emphasis={stats.chipsLoaded.length > 0}
            />
          </div>
        </div>
        <button
          className="btn btn-ghost btn-xs text-error flex-shrink-0"
          onClick={handleDelete}
          disabled={deleteCryostat.isPending}
          title="Delete cryostat"
        >
          <Trash2 className="h-3 w-3" />
        </button>
      </div>

      <div className="mt-5 space-y-4">
        {/* Active cool-down banner */}
        {activeCooldown && (
          <ActiveCooldownBanner
            cooldown={activeCooldown}
            isSelected={expandedId === activeCooldown.cooldown_id}
            onSelect={() => handleSelectFromTimeline(activeCooldown.cooldown_id)}
          />
        )}

        {/* Timeline + new-cooldown button */}
        {sortedCooldowns.length > 0 ? (
          <div className="space-y-2">
            <CooldownTimeline
              cooldowns={sortedCooldowns}
              selectedId={expandedId}
              onSelect={handleSelectFromTimeline}
            />
            <div className="flex justify-end">
              <button
                className="btn btn-sm btn-ghost gap-1"
                onClick={onCreateCooldown}
                title="Start a new cool-down cycle"
              >
                <Plus className="h-3.5 w-3.5" />
                New cool-down
              </button>
            </div>
          </div>
        ) : (
          <EmptyCooldowns onCreate={onCreateCooldown} />
        )}

        {/* Cool-down list (accordion) */}
        {sortedCooldowns.length > 0 && (
          <div className="space-y-2">
            {sortedCooldowns.map((cd) => (
              <CooldownItem
                key={cd.cooldown_id}
                ref={(el) => {
                  if (el) itemRefs.current.set(cd.cooldown_id, el);
                  else itemRefs.current.delete(cd.cooldown_id);
                }}
                cooldown={cd}
                allChips={allChips}
                expanded={expandedId === cd.cooldown_id}
                onToggle={() =>
                  setExpandedId((cur) => (cur === cd.cooldown_id ? null : cd.cooldown_id))
                }
                onChange={onChange}
              />
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

function ActiveCooldownBanner({
  cooldown,
  isSelected,
  onSelect,
}: {
  cooldown: Cooldown;
  isSelected: boolean;
  onSelect: () => void;
}) {
  const start = new Date(cooldown.started_at);
  const days = daysBetween(start, new Date());
  return (
    <button
      onClick={onSelect}
      className={`group w-full text-left rounded-xl border bg-success/8 px-4 py-3 transition-all hover:bg-success/12 ${
        isSelected ? "border-success/60 ring-2 ring-success/30" : "border-success/30"
      }`}
    >
      <div className="flex items-center gap-3">
        <span className="relative inline-flex h-3 w-3 flex-shrink-0">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success/60" />
          <span className="relative inline-flex h-3 w-3 rounded-full bg-success" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-sm">Currently cooling</span>
            <span className="font-mono font-bold text-sm">{cooldown.cooldown_id}</span>
            <span className="text-xs text-base-content/60 tabular-nums">
              · {formatRelativeDays(days)} ({formatDate(cooldown.started_at)})
            </span>
          </div>
          {cooldown.chip_ids.length > 0 && (
            <div className="mt-1 flex flex-wrap items-center gap-1.5 text-[11px] text-base-content/70">
              <span className="text-base-content/50">Chips:</span>
              {cooldown.chip_ids.map((id) => (
                <span
                  key={id}
                  className="rounded border border-base-300 bg-base-100 px-1.5 py-0.5 font-mono text-base-content/80"
                >
                  {id}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </button>
  );
}

function EmptyCooldowns({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="rounded-xl border border-dashed border-base-300 bg-base-200/30 px-4 py-8 text-center">
      <div className="text-sm text-base-content/70">No cool-downs yet</div>
      <div className="text-xs text-base-content/50 mt-0.5 mb-3">
        Cool-down cycles tag every calibration write with their{" "}
        <code className="font-mono">cooldown_id</code>.
      </div>
      <button className="btn btn-sm btn-primary gap-1" onClick={onCreate}>
        <Plus className="h-3.5 w-3.5" />
        Start a cool-down
      </button>
    </div>
  );
}
