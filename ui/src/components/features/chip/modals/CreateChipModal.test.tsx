import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  CreateChipModal,
  previousChipOnCryostat,
} from "@/components/features/chip/modals/CreateChipModal";

const mocks = vi.hoisted(() => ({
  mutate: vi.fn(),
  onSuccess: undefined as ((data: unknown) => void) | undefined,
  systems: [] as Array<{ system_id: string; backend: string; is_default: boolean }>,
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock("@/client/chip/chip", () => ({
  getListChipsQueryKey: () => ["chips"],
  useCreateChip: (options: { mutation: { onSuccess: (data: unknown) => void } }) => {
    mocks.onSuccess = options.mutation.onSuccess;
    return { mutate: mocks.mutate, isPending: false };
  },
  useListChips: () => ({ data: { data: { chips: [{ chip_id: "64Qv3" }, { chip_id: "64Qv2" }] } } }),
  useListChipSystems: (chipId: string) => ({
    data: chipId ? { data: { systems: mocks.systems } } : undefined,
  }),
}));

vi.mock("@/client/cooldown/cooldown", () => ({
  useListCooldowns: () => ({
    data: {
      data: {
        cooldowns: [
          {
            cooldown_id: "cd-1",
            cryo_id: "fridge-a",
            started_at: "2026-01-01T00:00:00",
            ended_at: "2026-03-01T00:00:00",
            chip_ids: ["64Qv2"],
          },
          {
            cooldown_id: "cd-2",
            cryo_id: "fridge-a",
            started_at: "2026-04-01T00:00:00",
            ended_at: null,
            chip_ids: [],
          },
        ],
      },
    },
  }),
}));

vi.mock("@/client/topology/topology", () => ({
  useListTopologies: () => ({
    isLoading: false,
    data: {
      data: {
        topologies: [{ id: "grid-64", name: "64-qubit grid", num_qubits: 64 }],
      },
    },
  }),
}));

describe("previousChipOnCryostat", () => {
  const cooldowns = [
    { cooldown_id: "a", cryo_id: "x", started_at: "2026-01-01", chip_ids: ["old"] },
    { cooldown_id: "b", cryo_id: "y", started_at: "2026-02-01", chip_ids: ["other"] },
    { cooldown_id: "c", cryo_id: "x", started_at: "2026-03-01", chip_ids: [] },
  ] as never[];

  it("returns the last chip of the previous cool-down on the same cryostat", () => {
    expect(previousChipOnCryostat(cooldowns, "c")).toBe("old");
    expect(previousChipOnCryostat(cooldowns, "a")).toBeNull();
    expect(previousChipOnCryostat(cooldowns, "missing")).toBeNull();
  });
});

describe("CreateChipModal", () => {
  afterEach(() => {
    cleanup();
    mocks.mutate.mockReset();
    mocks.systems = [];
  });

  it("validates the chip ID inline", async () => {
    render(<CreateChipModal isOpen onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Create Chip" }));

    expect(await screen.findByText("Chip ID is required")).toBeTruthy();
    expect(mocks.mutate).not.toHaveBeenCalled();
  });

  it("submits the normalized chip and selected topology", async () => {
    render(<CreateChipModal isOpen onClose={vi.fn()} />);
    fireEvent.change(screen.getByPlaceholderText("e.g., 64Q, Chip001"), {
      target: { value: "  chip-01  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create Chip" }));

    await waitFor(() =>
      expect(mocks.mutate).toHaveBeenCalledWith({
        data: {
          chip_id: "chip-01",
          size: 64,
          topology_id: "grid-64",
          display_name: undefined,
          cooldown_id: undefined,
          inherit_wiring_from: undefined,
          backend: undefined,
          provision_config: undefined,
        },
      }),
    );
  });

  it("preselects the cool-down, inherits from the previous chip on its cryostat, and its backend", async () => {
    mocks.systems = [{ system_id: "64Qv2", backend: "quel3", is_default: true }];
    render(<CreateChipModal isOpen onClose={vi.fn()} defaultCooldownId="cd-2" />);

    await waitFor(() =>
      expect((screen.getByLabelText("Inherit wiring from") as HTMLSelectElement).value).toBe(
        "64Qv2",
      ),
    );
    expect((screen.getByLabelText("Cool-down") as HTMLSelectElement).value).toBe("cd-2");
    await waitFor(() =>
      expect((screen.getByLabelText("Backend") as HTMLSelectElement).value).toBe("quel3"),
    );

    fireEvent.change(screen.getByPlaceholderText("e.g., 64Q, Chip001"), {
      target: { value: "64Qv4" },
    });
    fireEvent.change(screen.getByLabelText("Generate configuration files"), {
      target: { value: "on" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create Chip" }));

    await waitFor(() =>
      expect(mocks.mutate).toHaveBeenCalledWith({
        data: expect.objectContaining({
          chip_id: "64Qv4",
          cooldown_id: "cd-2",
          inherit_wiring_from: "64Qv2",
          backend: "quel3",
          provision_config: true,
        }),
      }),
    );
  });

  it("shows the provisioning result instead of closing when files were generated", async () => {
    const onClose = vi.fn();
    const onSuccess = vi.fn();
    render(<CreateChipModal isOpen onClose={onClose} onSuccess={onSuccess} />);

    mocks.onSuccess?.({
      data: {
        chip_id: "64Qv4",
        provisioning: {
          provisioned: true,
          layout: "shared",
          system_ids: ["64Qv4", "64Qv4-quel3"],
          inherited_from: "64Qv3",
          files: ["config/chip.yaml"],
          publish: { status: "failed", mode: "github", message: "remote rejected the push" },
          warnings: ["Wiring is empty"],
        },
      },
    });

    expect(await screen.findByText("Chip 64Qv4 created")).toBeTruthy();
    expect(screen.getByText("64Qv4-quel3")).toBeTruthy();
    expect(screen.getByText("Publish failed")).toBeTruthy();
    expect(screen.getByText("remote rejected the push")).toBeTruthy();
    expect(screen.getByText("Wiring is empty")).toBeTruthy();
    expect(onSuccess).toHaveBeenCalledWith("64Qv4");
    expect(onClose).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Close" }));
    expect(onClose).toHaveBeenCalled();
  });
});
