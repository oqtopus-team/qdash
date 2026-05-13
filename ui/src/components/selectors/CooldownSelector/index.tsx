"use client";

import { useMemo } from "react";

import Select, { type SingleValue } from "react-select";

import { useListCooldowns } from "@/client/cooldown/cooldown";
import type { CooldownResponse } from "@/schemas";
import { useSelectStyles } from "@/hooks/useSelectStyles";

interface CooldownOption {
  value: string;
  label: string;
}

interface CooldownSelectorProps {
  /** Restrict to cool-downs that contain this chip. Required. */
  chipId: string;
  /** Currently selected cool-down id, if any. */
  selectedCooldownId?: string | null;
  /** Called with the picked cool-down. */
  onPick: (cooldown: CooldownResponse) => void;
  placeholder?: string;
}

const DEFAULT_PLACEHOLDER = "Filter by cool-down…";

/**
 * Picks one of the chip's cool-downs and emits the full record. Matches
 * ChipSelector's react-select look. Callers decide how to apply the choice
 * (set a date range, jump to a date, set ``cooldown_id`` filter, etc.).
 */
export function CooldownSelector({
  chipId,
  selectedCooldownId,
  onPick,
  placeholder = DEFAULT_PLACEHOLDER,
}: CooldownSelectorProps) {
  const { data, isLoading, isError } = useListCooldowns(
    { chip_id: chipId || undefined },
    { query: { enabled: !!chipId, staleTime: 30_000 } },
  );
  const cooldowns = useMemo(
    () => data?.data?.cooldowns ?? [],
    [data?.data?.cooldowns],
  );

  const options = useMemo<CooldownOption[]>(
    () =>
      cooldowns.map((c) => ({
        value: c.cooldown_id,
        label: `${c.cooldown_id}${c.ended_at ? "" : " (active)"}`,
      })),
    [cooldowns],
  );

  const { minWidth, styles } = useSelectStyles<CooldownOption>({
    labels: options.map((o) => o.label),
    placeholder,
  });
  const selectedOption =
    options.find((option) => option.value === selectedCooldownId) ?? null;

  if (!chipId) return null;
  if (isLoading) {
    return (
      <div className="animate-pulse" style={{ minWidth }}>
        <div className="h-[38px] bg-base-300 rounded"></div>
      </div>
    );
  }
  if (isError) {
    return <div className="text-error text-sm">Failed to load cool-downs</div>;
  }
  if (options.length === 0) return null;

  const handleChange = (option: SingleValue<CooldownOption>) => {
    if (!option) return;
    const cd = cooldowns.find((c) => c.cooldown_id === option.value);
    if (!cd) return;
    onPick(cd);
  };

  return (
    <Select<CooldownOption>
      options={options}
      value={selectedOption}
      onChange={handleChange}
      placeholder={placeholder}
      isClearable={false}
      className="text-base-content"
      styles={styles}
    />
  );
}
