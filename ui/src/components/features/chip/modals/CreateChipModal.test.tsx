import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CreateChipModal } from "@/components/features/chip/modals/CreateChipModal";

const mocks = vi.hoisted(() => ({
  mutate: vi.fn(),
  configSources: {
    available: true,
    sources: [{ system_id: "64Qv3", backend: "quel1", mux_count: 16, files: ["box.yaml"] }],
  },
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock("@/client/chip/chip", () => ({
  getListChipsQueryKey: () => ["chips"],
  useCreateChip: () => ({ mutate: mocks.mutate, isPending: false }),
  useListChipConfigSources: () => ({ isLoading: false, data: { data: mocks.configSources } }),
}));

vi.mock("@/components/ui/Toast/useToast", () => ({
  useToast: () => ({ success: vi.fn(), info: vi.fn() }),
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

describe("CreateChipModal", () => {
  afterEach(() => {
    cleanup();
    mocks.mutate.mockReset();
    mocks.configSources.available = true;
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
          config: { backend: "quel1" },
        },
      }),
    );
  });

  it("copies wiring from the selected system", async () => {
    render(<CreateChipModal isOpen onClose={vi.fn()} />);
    fireEvent.change(screen.getByPlaceholderText("e.g., 64Q, Chip001"), {
      target: { value: "64Qv4" },
    });
    fireEvent.change(screen.getByLabelText("Wiring"), { target: { value: "64Qv3" } });
    expect(screen.queryByLabelText("Backend")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Create Chip" }));

    await waitFor(() =>
      expect(mocks.mutate).toHaveBeenCalledWith({
        data: {
          chip_id: "64Qv4",
          size: 64,
          topology_id: "grid-64",
          config: { source_system_id: "64Qv3" },
        },
      }),
    );
  });

  it("creates only the chip record when configuration is turned off", async () => {
    render(<CreateChipModal isOpen onClose={vi.fn()} />);
    fireEvent.change(screen.getByPlaceholderText("e.g., 64Q, Chip001"), {
      target: { value: "64Qv4" },
    });
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(screen.getByRole("button", { name: "Create Chip" }));

    await waitFor(() =>
      expect(mocks.mutate).toHaveBeenCalledWith({
        data: { chip_id: "64Qv4", size: 64, topology_id: "grid-64", config: { create: false } },
      }),
    );
  });

  it("explains when no configuration tree is mounted", async () => {
    mocks.configSources.available = false;
    render(<CreateChipModal isOpen onClose={vi.fn()} />);

    expect(screen.getByText(/No Qubex configuration tree is mounted/)).toBeTruthy();
    expect(screen.queryByLabelText("Wiring")).toBeNull();
  });
});
