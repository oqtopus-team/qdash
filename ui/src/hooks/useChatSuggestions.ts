"use client";

import { useMemo } from "react";
import {
  FileCode,
  FlaskConical,
  GitCompare,
  History,
  LineChart,
  ListChecks,
  Sparkles,
  Terminal,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { useListChipQubits, useListChips } from "@/client/chip/chip";
import { useGetCopilotSystemPrompt } from "@/client/copilot/copilot";
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
 * asks for a plan, which is read-only; running it is a separate approval. The
 * workspace suggestion has the model write and run a script (code streams into
 * the trace as it is typed), and the flow suggestion ends in a save that waits
 * for approval; neither touches hardware. Both appear only when the runtime
 * offers the tools they need (`tools`: the names the system prompt view lists;
 * null while unknown), so a starter prompt never asks for what the chat lacks.
 */
export function buildGeneralSuggestions(
  chipId: string | null,
  qids: string[],
  tools: ReadonlySet<string> | null = null,
): ChatSuggestion[] {
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
  const workspace = `Fetch ${qa}'s recent T1 values, write a Python script in the workspace that fits their drift, and run it`;
  const flow = `Write a flow from the "simple" template that runs CheckT1 on ${a !== undefined ? `qubit ${a}` : "qubit 0"} and save it as t1_check_${a ?? "0"}`;
  return [
    { text: pipeline, Icon: Workflow },
    ...(tools?.has("bash") ? [{ text: workspace, Icon: Terminal }] : []),
    ...(tools?.has("qdash_save_flow") ? [{ text: flow, Icon: FileCode }] : []),
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
  // Which tools this deployment's runtime offers (workspace, flow saving); a
  // backend without the runtime answers 503, and those suggestions stay hidden.
  const prompt = useGetCopilotSystemPrompt({
    query: { enabled: !isAnalysis, staleTime: 300_000, retry: false },
  });
  const toolNames = prompt.data?.data?.tools;
  const tools = useMemo(() => (toolNames ? new Set(toolNames) : null), [toolNames]);
  return useMemo(
    () => (isAnalysis ? ANALYSIS_SUGGESTIONS : buildGeneralSuggestions(chipId, qids, tools)),
    [isAnalysis, chipId, qids, tools],
  );
}
