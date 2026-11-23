"use client";

import { useMemo } from "react";
import {
  FlaskConical,
  GitCompare,
  LineChart,
  ListChecks,
  Sparkles,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { useListChipQubits, useListChips } from "@/client/chip/chip";
import type { ChipResponse } from "@/schemas";

export interface ChatSuggestion {
  text: string;
  Icon: LucideIcon;
}

const ANALYSIS_SUGGESTIONS: ChatSuggestion[] = [
  { text: "How should I interpret this result?", Icon: FlaskConical },
  { text: "Is this value within expected range?", Icon: ListChecks },
  { text: "What could cause this issue?", Icon: GitCompare },
  { text: "What should I try next?", Icon: Sparkles },
];

/** The chip a fresh chat most likely concerns: active first, then newest. */
export function pickChip(chips: ChipResponse[] | undefined): ChipResponse | null {
  if (!chips?.length) return null;
  const ranked = [...chips].sort((a, b) => {
    const activeA = a.activity_status === "active" ? 0 : 1;
    const activeB = b.activity_status === "active" ? 0 : 1;
    if (activeA !== activeB) return activeA - activeB;
    return String(b.installed_at ?? "").localeCompare(String(a.installed_at ?? ""));
  });
  return ranked[0];
}

function label(qid: string): string {
  return /^\d+$/.test(qid) ? `Q${qid.padStart(2, "0")}` : qid;
}

/**
 * The three starter prompts for an empty general chat: a T1 trend, the current
 * parameters, and a calibration plan, aimed at the first qubit of the chip a
 * fresh chat most likely concerns.
 *
 * Chips and qubit ids differ per deployment, so the prompts name a real qubit
 * instead of a fixed "Q00". Without a known qubit they stay generic rather than
 * name one that may not exist. Planning is read-only; running a plan is a
 * separate approval.
 */
export function buildGeneralSuggestions(chipId: string | null, qids: string[]): ChatSuggestion[] {
  const [first] = qids;
  const qubit = first !== undefined ? label(first) : null;
  const on = chipId ? ` on ${chipId}` : "";
  return [
    { text: qubit ? `Show T1 trend for ${qubit}` : "Show T1 trend", Icon: LineChart },
    {
      text: qubit ? `What are ${qubit}'s current parameters?` : "What are the current parameters?",
      Icon: ListChecks,
    },
    {
      text: qubit ? `Plan a calibration for ${qubit}${on}` : `Plan a calibration${on}`,
      Icon: Workflow,
    },
  ];
}

export function useChatSuggestions(isAnalysis: boolean): ChatSuggestion[] {
  const chips = useListChips({ query: { staleTime: 60_000, enabled: !isAnalysis } });
  const chip = useMemo(() => pickChip(chips.data?.data?.chips), [chips.data?.data?.chips]);
  const chipId = chip?.chip_id ?? null;
  const qubits = useListChipQubits(
    chipId ?? "",
    { limit: 1 },
    { query: { enabled: !isAnalysis && Boolean(chipId), staleTime: 60_000 } },
  );
  const qids = useMemo(
    () => (qubits.data?.data?.qubits ?? []).map((q) => q.qid),
    [qubits.data?.data?.qubits],
  );
  return useMemo(
    () => (isAnalysis ? ANALYSIS_SUGGESTIONS : buildGeneralSuggestions(chipId, qids)),
    [isAnalysis, chipId, qids],
  );
}
