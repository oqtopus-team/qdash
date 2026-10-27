import type { ChipSystemInfo } from "@/schemas";

/** Qubit IDs of a System from its MUX numbers and the MUX width of the topology. */
export function systemQids(system: ChipSystemInfo, muxWidth: number): Set<string> {
  const perMux = Math.max(1, muxWidth) ** 2;
  const qids = new Set<string>();
  for (const mux of system.mux_ids ?? []) {
    for (let offset = 0; offset < perMux; offset += 1) {
      qids.add(String(mux * perMux + offset));
    }
  }
  return qids;
}

/** Keep the entries whose qubit belongs to the System; `null` keeps everything. */
export function filterQubitEntries<T>(
  entries: Record<string, T> | undefined,
  qids: Set<string> | null,
): Record<string, T> | undefined {
  if (!entries || qids === null) return entries;
  const kept: Record<string, T> = {};
  for (const [qid, value] of Object.entries(entries)) {
    if (qids.has(qid)) kept[qid] = value;
  }
  return kept;
}

/** Keep the couplings (`"0-1"`) whose both qubits belong to the System. */
export function filterCouplingEntries<T>(
  entries: Record<string, T> | undefined,
  qids: Set<string> | null,
): Record<string, T> | undefined {
  if (!entries || qids === null) return entries;
  const kept: Record<string, T> = {};
  for (const [couplingId, value] of Object.entries(entries)) {
    const [control, target] = couplingId.split("-");
    if (qids.has(control) && qids.has(target)) kept[couplingId] = value;
  }
  return kept;
}
