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
  it("offers exactly three short prompts aimed at the chip's first qubit", () => {
    expect(buildGeneralSuggestions("64Qv3", ["0", "1"]).map((s) => s.text)).toEqual([
      "Show T1 trend for Q00",
      "What are Q00's current parameters?",
      "Plan a calibration for Q00 on 64Qv3",
    ]);
  });

  it("keeps non-numeric qubit ids as they are", () => {
    expect(buildGeneralSuggestions("chip", ["Q32"]).map((s) => s.text)).toEqual([
      "Show T1 trend for Q32",
      "What are Q32's current parameters?",
      "Plan a calibration for Q32 on chip",
    ]);
  });

  it("stays generic instead of naming a qubit that may not exist", () => {
    expect(buildGeneralSuggestions("chip", []).map((s) => s.text)).toEqual([
      "Show T1 trend",
      "What are the current parameters?",
      "Plan a calibration on chip",
    ]);
    expect(buildGeneralSuggestions(null, []).map((s) => s.text)).toEqual([
      "Show T1 trend",
      "What are the current parameters?",
      "Plan a calibration",
    ]);
  });

  it("never offers workspace scripts or flow creation", () => {
    const texts = buildGeneralSuggestions("chip", ["0"]).map((s) => s.text);
    expect(texts.some((t) => /workspace|script|flow|save it as/i.test(t))).toBe(false);
  });
});

describe("useChatSuggestions", () => {
  it("asks for the active chip's first qubit and builds from it", () => {
    listChips.mockReturnValue({
      data: { data: { chips: [{ chip_id: "64Qv3", activity_status: "active" }] } },
    });
    listChipQubits.mockReturnValue({
      data: { data: { qubits: [{ qid: "4" }] } },
    });
    const { result } = renderHook(() => useChatSuggestions(false));

    expect(listChipQubits).toHaveBeenCalledWith(
      "64Qv3",
      { limit: 1 },
      expect.objectContaining({ query: expect.objectContaining({ enabled: true }) }),
    );
    expect(result.current.map((s) => s.text)).toEqual([
      "Show T1 trend for Q04",
      "What are Q04's current parameters?",
      "Plan a calibration for Q04 on 64Qv3",
    ]);
  });

  it("falls back to generic prompts while chips and qubits are unknown", () => {
    listChips.mockReturnValue({ data: undefined });
    listChipQubits.mockReturnValue({ data: undefined });
    const { result } = renderHook(() => useChatSuggestions(false));
    expect(result.current.map((s) => s.text)).toEqual([
      "Show T1 trend",
      "What are the current parameters?",
      "Plan a calibration",
    ]);
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
      { limit: 1 },
      expect.objectContaining({ query: expect.objectContaining({ enabled: false }) }),
    );
    expect(result.current.map((s) => s.text)).toContain("How should I interpret this result?");
  });
});
