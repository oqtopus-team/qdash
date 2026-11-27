"use client";

import { forwardRef, useId, useMemo, useState } from "react";

import { zodResolver } from "@hookform/resolvers/zod";
import { ChevronDown, ChevronRight, Plus, Trash2, X } from "lucide-react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import {
  useAssignChipToCooldown,
  useDeleteCooldown,
  useUnassignChipFromCooldown,
  useUpdateCooldown,
} from "@/client/cooldown/cooldown";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { SelectedLabel } from "@/components/ui/SelectedLabel";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";
import { getApiErrorMessage } from "@/lib/utils/apiError";
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

/** Zod schema for the cooldown date form; the end date is optional but not before the start. */
const cooldownDatesSchema = z
  .object({
    startedAt: z.string().min(1, "Start date is required"),
    endedAt: z.string(),
  })
  .refine((values) => !values.endedAt || !values.startedAt || values.endedAt >= values.startedAt, {
    message: "End date must be on or after the start date",
    path: ["endedAt"],
  });

type CooldownDatesFormValues = z.infer<typeof cooldownDatesSchema>;

/** Returns the date form values for the cooldown's current dates. */
function cooldownToDateValues(cooldown: Cooldown): CooldownDatesFormValues {
  return {
    startedAt: isoToDateInput(cooldown.started_at),
    endedAt: isoToDateInput(cooldown.ended_at),
  };
}

function formatDateRange(startedAt: string, endedAt: string | null | undefined): string {
  const start = formatDate(startedAt);
  if (!endedAt) return `${start} → now`;
  return `${start} → ${formatDate(endedAt)}`;
}

export const CooldownItem = forwardRef<HTMLDivElement, CooldownItemProps>(function CooldownItem(
  { cooldown, allChips, expanded, onToggle, onChange },
  ref,
) {
  const updateMutation = useUpdateCooldown();
  const deleteMutation = useDeleteCooldown();
  const assignMutation = useAssignChipToCooldown();
  const unassignMutation = useUnassignChipFromCooldown();
  const [chipToAdd, setChipToAdd] = useState("");
  const [confirmation, setConfirmation] = useState<"end" | "delete" | null>(null);
  const contentId = useId();
  const isActive = !cooldown.ended_at;

  // Dates: click-to-edit
  const [editingDates, setEditingDates] = useState(false);
  const [dateServerError, setDateServerError] = useState<string | null>(null);
  const startedAtId = useId();
  const endedAtId = useId();
  const startedAtErrorId = `${startedAtId}-error`;
  const endedAtErrorId = `${endedAtId}-error`;
  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm<CooldownDatesFormValues>({
    resolver: zodResolver(cooldownDatesSchema),
    defaultValues: cooldownToDateValues(cooldown),
  });
  const draftStartedAt = watch("startedAt");

  const availableChips = useMemo(
    () => allChips.filter((c) => !cooldown.chip_ids.includes(c)),
    [allChips, cooldown.chip_ids],
  );

  /** Opens the date editor with values reset from the current cooldown. */
  const startEditingDates = () => {
    reset(cooldownToDateValues(cooldown));
    setDateServerError(null);
    setEditingDates(true);
  };

  /** Closes the date editor and discards the draft values. */
  const cancelEditingDates = () => {
    reset(cooldownToDateValues(cooldown));
    setDateServerError(null);
    setEditingDates(false);
  };

  /** Saves the dates and surfaces API failures as a server error. */
  const handleSaveDates = async (values: CooldownDatesFormValues) => {
    setDateServerError(null);
    try {
      await updateMutation.mutateAsync({
        cooldownId: cooldown.cooldown_id,
        data: {
          started_at: dateInputToIso(values.startedAt),
          ended_at: values.endedAt ? dateInputToIso(values.endedAt, true) : null,
        },
      });
    } catch (err) {
      setDateServerError(getApiErrorMessage(err, "Failed to update cool-down dates"));
      return;
    }
    setEditingDates(false);
    onChange();
  };

  const handleEnd = async () => {
    await updateMutation.mutateAsync({
      cooldownId: cooldown.cooldown_id,
      data: { ended_at: new Date().toISOString() },
    });
    setConfirmation(null);
    onChange();
  };

  const handleDelete = async () => {
    await deleteMutation.mutateAsync({ cooldownId: cooldown.cooldown_id });
    setConfirmation(null);
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
      className={`rounded-[var(--radius-box)] border transition-colors ${
        isActive ? "border-success/40 bg-success/5" : "border-base-300 bg-base-100"
      }`}
    >
      <div
        className={`flex items-center ${expanded ? "rounded-t-xl" : "rounded-[var(--radius-box)]"}`}
      >
        <button
          type="button"
          onClick={onToggle}
          className={`min-w-0 flex flex-1 items-center gap-2 px-3 py-2 text-left hover:bg-base-200/40 ${
            expanded ? "rounded-tl-xl" : "rounded-l-xl"
          }`}
          aria-expanded={expanded}
          aria-controls={contentId}
        >
          {expanded ? (
            <ChevronDown className="h-4 w-4 flex-shrink-0 text-base-content/50" />
          ) : (
            <ChevronRight className="h-4 w-4 flex-shrink-0 text-base-content/50" />
          )}
          <span className="min-w-0 flex flex-1 items-center gap-2 flex-wrap">
            <span className="font-mono font-medium text-sm">{cooldown.cooldown_id}</span>
            <span className={`badge badge-xs ${isActive ? "badge-success" : "badge-ghost"}`}>
              {isActive ? "active" : "ended"}
            </span>
            <span className="text-xs text-base-content/60 tabular-nums">
              {formatDateRange(cooldown.started_at, cooldown.ended_at)}
            </span>
            <span className="text-xs text-base-content/50">
              · {cooldown.chip_ids.length} chip
              {cooldown.chip_ids.length !== 1 ? "s" : ""}
            </span>
          </span>
        </button>
        <div className="flex gap-1 flex-shrink-0 pr-2">
          {isActive && (
            <button
              type="button"
              className="btn btn-xs btn-warning"
              onClick={() => setConfirmation("end")}
              disabled={updateMutation.isPending}
              title="End this cool-down (warm-up)"
            >
              End now
            </button>
          )}
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                className="btn btn-xs btn-square btn-ghost text-error"
                onClick={() => setConfirmation("delete")}
                disabled={deleteMutation.isPending}
                aria-label="Delete this cool-down"
              >
                <Trash2 className="h-3 w-3" aria-hidden="true" />
              </button>
            </TooltipTrigger>
            <TooltipContent>Delete this cool-down</TooltipContent>
          </Tooltip>
        </div>
      </div>

      {/* Expanded body */}
      {expanded && (
        <div id={contentId} className="px-4 pb-4 pt-1 space-y-4 border-t border-base-300">
          {/* Dates inline edit */}
          <div className="text-xs">
            <div className="text-base-content/60 font-medium mb-1">Dates</div>
            {!editingDates ? (
              <button
                type="button"
                onClick={startEditingDates}
                className="text-base-content/80 inline-flex items-center gap-1.5 rounded px-1 -ml-1 hover:bg-base-200 transition-colors tabular-nums"
                title="Edit dates"
              >
                {formatDateRange(cooldown.started_at, cooldown.ended_at)}
                {isActive && <span className="text-success/80 ml-1">· still active</span>}
              </button>
            ) : (
              <form onSubmit={handleSubmit(handleSaveDates)} noValidate>
                <div className="flex flex-wrap items-start gap-2">
                  <div className="flex flex-col">
                    <label htmlFor={startedAtId} className="text-xs text-base-content/60">
                      Started
                    </label>
                    <input
                      id={startedAtId}
                      type="date"
                      className={`input input-xs input-bordered tabular-nums${
                        errors.startedAt ? " input-error" : ""
                      }`}
                      {...register("startedAt")}
                      aria-invalid={Boolean(errors.startedAt)}
                      aria-describedby={errors.startedAt ? startedAtErrorId : undefined}
                      disabled={updateMutation.isPending}
                      autoFocus
                    />
                    {errors.startedAt && (
                      <p id={startedAtErrorId} className="mt-1 w-0 min-w-full text-xs text-error">
                        {errors.startedAt.message}
                      </p>
                    )}
                  </div>
                  <div className="flex flex-col">
                    <label htmlFor={endedAtId} className="text-xs text-base-content/60">
                      Ended (empty = active)
                    </label>
                    <input
                      id={endedAtId}
                      type="date"
                      className={`input input-xs input-bordered tabular-nums${
                        errors.endedAt ? " input-error" : ""
                      }`}
                      {...register("endedAt")}
                      min={draftStartedAt || undefined}
                      aria-invalid={Boolean(errors.endedAt)}
                      aria-describedby={errors.endedAt ? endedAtErrorId : undefined}
                      disabled={updateMutation.isPending}
                    />
                    {errors.endedAt && (
                      <p id={endedAtErrorId} className="mt-1 w-0 min-w-full text-xs text-error">
                        {errors.endedAt.message}
                      </p>
                    )}
                  </div>
                  <div className="flex gap-2 pt-4">
                    <button
                      type="submit"
                      className="btn btn-xs btn-primary"
                      disabled={updateMutation.isPending}
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      className="btn btn-xs btn-ghost"
                      onClick={cancelEditingDates}
                    >
                      Cancel
                    </button>
                  </div>
                </div>
                {dateServerError && (
                  <div className="alert alert-error mt-2 py-2 text-xs" role="alert">
                    <span>{dateServerError}</span>
                  </div>
                )}
              </form>
            )}
          </div>

          {/* Chip management */}
          <div className="text-xs">
            <div className="text-base-content/60 font-medium mb-1">
              Chips loaded
              <span className="text-base-content/40 normal-case font-normal ml-1">
                ({cooldown.chip_ids.length})
              </span>
            </div>
            <div className="flex flex-wrap gap-1.5 items-center">
              {cooldown.chip_ids.length === 0 && (
                <span className="text-base-content/40 italic">No chips loaded.</span>
              )}
              {cooldown.chip_ids.map((chipId) => (
                <span key={chipId} className="badge badge-outline badge-md gap-1 pr-1 font-mono">
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
                    <SelectedLabel />
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
      <ConfirmDialog
        open={confirmation !== null}
        title={confirmation === "end" ? "End cool-down?" : "Delete cool-down?"}
        description={
          confirmation === "end"
            ? `End cool-down ${cooldown.cooldown_id} now?`
            : `Delete cool-down ${cooldown.cooldown_id}? This action cannot be undone.`
        }
        confirmLabel={confirmation === "end" ? "End cool-down" : "Delete cool-down"}
        onConfirm={confirmation === "end" ? handleEnd : handleDelete}
        onOpenChange={(open) => !open && setConfirmation(null)}
        pending={updateMutation.isPending || deleteMutation.isPending}
        destructive={confirmation === "delete"}
      />
    </div>
  );
});
