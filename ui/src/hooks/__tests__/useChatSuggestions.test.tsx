import { renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { buildGeneralSuggestions, pickChip, useChatSuggestions } from "../useChatSuggestions";

const listChips = vi.fn();
const listChipQubits = vi.fn();
vi.mock("@/client/chip/chip", () => ({
  useListChips: (...args: unknown[]) => listChips(...args),
  useListChipQubits: (...args: unknown[]) => listChipQubits(...args),
}));

describe("pickChip", () => {
  it("prefers the active chip, then the newest", () => {
    const chips = [
      { chip_id: "old", activity_status: "inactive", installed_at: "2026-01-01T00:00:00Z" },
      { chip_id: "new", activity_status: "inactive", installed_at: "2026-09-01T00:00:00Z" },
      { chip_id: "live", activity_status: "active", installed_at: "2026-03-01T00:00:00Z" },
    ] as never[];
    expect(pickChip(chips)?.chip_id).toBe("live");
    expect(pickChip(chips.slice(0, 2))?.chip_id).toBe("new");
    expect(pickChip([])).toBeNull();
    expect(pickChip(undefined)).toBeNull();
  });
});

describe("buildGeneralSuggestions", () => {
  it("names the chip's first qubits and leads with a pipeline plan", () => {
    const texts = buildGeneralSuggestions("64Qv3", ["0", "1"]).map((s) => s.text);
    expect(texts[0]).toBe(
      "Plan a calibration on 64Qv3: coarse one-qubit check on qubits 0 and 1, then T1 and T2 on the ones that pass",
    );
    expect(texts).toContain("Show T1 trend for Q00");
    expect(texts).toContain("Compare T1 and T2 for Q01");
  });

  it("keeps non-numeric qubit ids as they are and copes with one qubit", () => {
    const texts = buildGeneralSuggestions("chip", ["Q32"]).map((s) => s.text);
    expect(texts[0]).toBe(
      "Plan a calibration on chip: coarse one-qubit check on qubit Q32, then T1 and T2 on the ones that pass",
    );
    expect(texts).toContain("Compare T1 and T2 for Q32");
  });

  it("falls back to MUX 0 and generic ids when nothing is known", () => {
    const texts = buildGeneralSuggestions(null, []).map((s) => s.text);
    expect(texts[0]).toBe(
      "Plan a calibration: coarse one-qubit check on MUX 0, then T1 and T2 on the ones that pass",
    );
    expect(texts).toContain("Show T1 trend for Q00");
  });
});

describe("useChatSuggestions", () => {
  it("asks for the active chip's first two qubits and builds from them", () => {
    listChips.mockReturnValue({
      data: { data: { chips: [{ chip_id: "64Qv3", activity_status: "active" }] } },
    });
    listChipQubits.mockReturnValue({
      data: { data: { qubits: [{ qid: "4" }, { qid: "5" }] } },
    });
    const { result } = renderHook(() => useChatSuggestions(false));

    expect(listChipQubits).toHaveBeenCalledWith(
      "64Qv3",
      { limit: 2 },
      expect.objectContaining({ query: expect.objectContaining({ enabled: true }) }),
    );
    expect(result.current[0].text).toMatch(/on 64Qv3: coarse one-qubit check on qubits 4 and 5/);
  });

  it("does not fetch for analysis chats and returns the analysis prompts", () => {
    listChips.mockClear();
    listChipQubits.mockClear();
    listChips.mockReturnValue({ data: undefined });
    listChipQubits.mockReturnValue({ data: undefined });
    const { result } = renderHook(() => useChatSuggestions(true));

    expect(listChips).toHaveBeenCalledWith(
      expect.objectContaining({ query: expect.objectContaining({ enabled: false }) }),
    );
    expect(listChipQubits).toHaveBeenCalledWith(
      "",
      { limit: 2 },
      expect.objectContaining({ query: expect.objectContaining({ enabled: false }) }),
    );
    expect(result.current.map((s) => s.text)).toContain("How should I interpret this result?");
  });
});
