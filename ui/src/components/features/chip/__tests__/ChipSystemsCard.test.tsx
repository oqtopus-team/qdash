import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChipSystemsCard } from "@/components/features/chip/ChipSystemsCard";
import { parseMuxIds } from "@/components/features/chip/modals/AddChipSystemModal";

const mocks = vi.hoisted(() => ({
  mutate: vi.fn(),
  response: null as Record<string, unknown> | null,
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock("@/client/chip/chip", () => ({
  getListChipSystemsQueryKey: (chipId: string) => ["systems", chipId],
  useListChipSystems: () => ({ data: mocks.response ? { data: mocks.response } : undefined }),
  useAddChipSystem: () => ({ mutate: mocks.mutate, isPending: false }),
}));

const quel1 = {
  system_id: "64Qv3",
  chip_id: "64Qv3",
  driver: "qubex",
  backend: "quel1",
  mux_ids: [0, 1, 2, 3],
  box_ids: ["Q73A", "R21B"],
  is_default: true,
  has_params: true,
  has_calib_note: false,
};

describe("parseMuxIds", () => {
  it("accepts comma or space separated integers and rejects anything else", () => {
    expect(parseMuxIds("8, 9 10,9")).toEqual([8, 9, 10]);
    expect(parseMuxIds("8, x")).toBeNull();
    expect(parseMuxIds("")).toEqual([]);
  });
});

describe("ChipSystemsCard", () => {
  afterEach(() => {
    cleanup();
    mocks.mutate.mockReset();
    mocks.response = null;
  });

  it("stays hidden for a legacy chip with its single implicit System", () => {
    mocks.response = { chip_id: "64Qv3", layout: "legacy", provisionable: false, systems: [quel1] };
    render(<ChipSystemsCard chipId="64Qv3" canEdit />);
    expect(screen.queryByTestId("chip-systems-card")).toBeNull();
  });

  it("lists every System and submits a new one with the moved MUXes", async () => {
    mocks.response = {
      chip_id: "64Qv3",
      layout: "shared",
      provisionable: true,
      systems: [
        quel1,
        { ...quel1, system_id: "64Qv3-quel3", backend: "quel3", is_default: false, mux_ids: [4] },
      ],
    };
    render(<ChipSystemsCard chipId="64Qv3" canEdit />);

    expect(screen.getByText("64Qv3-quel3")).toBeTruthy();
    expect(screen.getByText("default")).toBeTruthy();
    expect(screen.getAllByText("Q73A, R21B")).toHaveLength(2);

    fireEvent.click(screen.getByRole("button", { name: /add system/i }));
    expect(await screen.findByText("Every backend already has a System")).toBeTruthy();
    expect((screen.getByRole("button", { name: "Add" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("adds a System on the free backend", async () => {
    mocks.response = { chip_id: "64Qv3", layout: "shared", provisionable: true, systems: [quel1] };
    render(<ChipSystemsCard chipId="64Qv3" canEdit />);

    fireEvent.click(screen.getByRole("button", { name: /add system/i }));
    expect((screen.getByLabelText("Backend") as HTMLSelectElement).value).toBe("quel3");
    fireEvent.change(screen.getByLabelText("MUX numbers"), { target: { value: "8, 9" } });
    fireEvent.change(screen.getByLabelText(/^Backend settings/), {
      target: { value: '{"clock_master": "10.0.0.1"}' },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add" }));

    await waitFor(() =>
      expect(mocks.mutate).toHaveBeenCalledWith({
        chipId: "64Qv3",
        data: { backend: "quel3", mux_ids: [8, 9], settings: { clock_master: "10.0.0.1" } },
      }),
    );
  });

  it("hides the action for viewers", () => {
    mocks.response = { chip_id: "64Qv3", layout: "shared", provisionable: true, systems: [quel1] };
    render(<ChipSystemsCard chipId="64Qv3" canEdit={false} />);
    expect(screen.getByTestId("chip-systems-card")).toBeTruthy();
    expect(screen.queryByRole("button", { name: /add system/i })).toBeNull();
  });
});
