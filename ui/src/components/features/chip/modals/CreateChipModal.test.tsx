import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CreateChipModal } from "@/components/features/chip/modals/CreateChipModal";

const mocks = vi.hoisted(() => ({
  mutate: vi.fn(),
  isLoadingSources: false,
  isConfigSourcesError: false,
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
  useListChipConfigSources: () => ({
    isLoading: mocks.isLoadingSources,
    isError: mocks.isConfigSourcesError,
    data:
      mocks.isLoadingSources || mocks.isConfigSourcesError
        ? undefined
        : { data: mocks.configSources },
  }),
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
    mocks.isLoadingSources = false;
    mocks.isConfigSourcesError = false;
  });

  it("validates the chip ID inline", async () => {
    render(<CreateChipModal isOpen onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Create Chip" }));

    expect(await screen.findByText("Chip ID is required")).toBeTruthy();
    expect(mocks.mutate).not.toHaveBeenCalled();
  });

  it("waits for configuration availability before submitting", async () => {
    mocks.isLoadingSources = true;
    const onClose = vi.fn();
    const { rerender } = render(<CreateChipModal isOpen onClose={onClose} />);
    const input = screen.getByPlaceholderText("e.g., 64Q, Chip001");
    fireEvent.change(input, { target: { value: "chip-01" } });
    expect(screen.getByRole("button", { name: "Create Chip" })).toBeDisabled();
    await act(async () => {
      fireEvent.submit(input.closest("form")!);
    });
    expect(mocks.mutate).not.toHaveBeenCalled();

    mocks.isLoadingSources = false;
    rerender(<CreateChipModal isOpen onClose={onClose} />);
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

  it("blocks submission on configuration errors and recovers after a successful query", async () => {
    mocks.isConfigSourcesError = true;
    const onClose = vi.fn();
    const { rerender } = render(<CreateChipModal isOpen onClose={onClose} />);
    const input = screen.getByPlaceholderText("e.g., 64Q, Chip001");
    fireEvent.change(input, { target: { value: "chip-01" } });
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Unable to check the Qubex configuration tree",
    );
    expect(screen.queryByText(/No Qubex configuration tree is mounted/)).toBeNull();
    expect(screen.getByRole("button", { name: "Create Chip" })).toBeDisabled();
    await act(async () => {
      fireEvent.submit(input.closest("form")!);
    });
    expect(mocks.mutate).not.toHaveBeenCalled();

    mocks.isConfigSourcesError = false;
    rerender(<CreateChipModal isOpen onClose={onClose} />);
    expect(screen.queryByRole("alert")).toBeNull();
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

  it("creates configuration from the selected backend template", async () => {
    render(<CreateChipModal isOpen onClose={vi.fn()} />);
    expect(screen.getByRole("option", { name: "Start from template" })).toBeTruthy();
    fireEvent.change(screen.getByPlaceholderText("e.g., 64Q, Chip001"), {
      target: { value: "new-chip" },
    });
    fireEvent.change(screen.getByLabelText("Backend"), { target: { value: "quel3" } });
    fireEvent.click(screen.getByRole("button", { name: "Create Chip" }));
    await waitFor(() =>
      expect(mocks.mutate).toHaveBeenCalledWith({
        data: {
          chip_id: "new-chip",
          size: 64,
          topology_id: "grid-64",
          config: { backend: "quel3" },
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
