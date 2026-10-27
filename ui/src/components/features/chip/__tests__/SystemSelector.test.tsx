import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ChipSystemInfo } from "@/schemas";

import { SystemSelector } from "../SystemSelector";

const mocks = vi.hoisted(() => ({ systems: vi.fn() }));

vi.mock("@/client/chip/chip", () => ({ useListChipSystems: mocks.systems }));

function system(systemId: string, backend: string, muxIds: number[]): ChipSystemInfo {
  return {
    system_id: systemId,
    chip_id: "144Qv3",
    driver: "qubex",
    backend,
    mux_ids: muxIds,
    is_default: systemId === "144Qv3",
    has_params: true,
    has_calib_note: true,
  };
}

function mockSystems(systems: ChipSystemInfo[]) {
  mocks.systems.mockReturnValue({
    data: { data: { chip_id: "144Qv3", layout: "shared", provisionable: true, systems } },
    isLoading: false,
  });
}

describe("SystemSelector", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders nothing for a chip with one System", () => {
    mockSystems([system("144Qv3", "quel1", [0, 1])]);
    const { container } = render(
      <SystemSelector chipId="144Qv3" selectedSystemId={null} onSelect={vi.fn()} />,
    );
    expect(container.innerHTML).toBe("");
  });

  it("offers every System and reports the choice", () => {
    mockSystems([system("144Qv3", "quel1", [0, 1]), system("144Qv3-quel3", "quel3", [2])]);
    const onSelect = vi.fn();
    render(<SystemSelector chipId="144Qv3" selectedSystemId="144Qv3" onSelect={onSelect} />);

    expect(screen.getByRole("group", { name: "System" })).toBeTruthy();
    expect(
      screen.getByRole("button", { name: "144Qv3 (quel1)" }).getAttribute("aria-pressed"),
    ).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "144Qv3-quel3 (quel3)" }));
    expect(onSelect).toHaveBeenCalledWith("144Qv3-quel3");
    fireEvent.click(screen.getByRole("button", { name: "All Systems" }));
    expect(onSelect).toHaveBeenCalledWith(null);
  });

  it("clears a selection the chip no longer has", () => {
    mockSystems([system("144Qv3", "quel1", [0, 1]), system("144Qv3-quel3", "quel3", [2])]);
    const onSelect = vi.fn();
    render(<SystemSelector chipId="144Qv3" selectedSystemId="gone" onSelect={onSelect} />);
    expect(onSelect).toHaveBeenCalledWith(null);
  });
});
