"use client";

import { useMemo } from "react";
import {
  FlaskConical,
  GitCompare,
  History,
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
 * Suggestions for the empty chat, written for the qubits that exist here.
 *
 * Chips and qubit ids differ per deployment, so the examples name the first
 * qubits of the active chip instead of a fixed "Q00". The pipeline suggestion
 * asks for a plan, which is read-only; running it is a separate approval.
 */
export function buildGeneralSuggestions(chipId: string | null, qids: string[]): ChatSuggestion[] {
  const [a, b] = qids;
  const qa = a !== undefined ? label(a) : "Q00";
  const qb = b !== undefined ? label(b) : a !== undefined ? label(a) : "Q01";
  const on = chipId ? ` on ${chipId}` : "";
  // The plan names raw qubit ids: that is what the pipeline spec takes, so the
  // agent does not have to translate a display label back into an id.
  const pipeline =
    a !== undefined
      ? `Plan a calibration${on}: coarse one-qubit check on ${b !== undefined ? `qubits ${a} and ${b}` : `qubit ${a}`}, then T1 and T2 on the ones that pass`
      : `Plan a calibration${on}: coarse one-qubit check on MUX 0, then T1 and T2 on the ones that pass`;
  return [
    { text: pipeline, Icon: Workflow },
    { text: `Show T1 trend for ${qa}`, Icon: LineChart },
    { text: `What are ${qa}'s current parameters?`, Icon: ListChecks },
    { text: `Compare T1 and T2 for ${qb}`, Icon: GitCompare },
    { text: `Show gate fidelity history for ${qa}`, Icon: History },
  ];
}

export function useChatSuggestions(isAnalysis: boolean): ChatSuggestion[] {
  const chips = useListChips({ query: { staleTime: 60_000, enabled: !isAnalysis } });
  const chip = useMemo(() => pickChip(chips.data?.data?.chips), [chips.data?.data?.chips]);
  const chipId = chip?.chip_id ?? null;
  const qubits = useListChipQubits(
    chipId ?? "",
    { limit: 2 },
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
