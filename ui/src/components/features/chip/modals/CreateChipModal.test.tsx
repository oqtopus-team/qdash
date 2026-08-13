import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CreateChipModal } from "@/components/features/chip/modals/CreateChipModal";

const mocks = vi.hoisted(() => ({ mutate: vi.fn() }));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock("@/client/chip/chip", () => ({
  getListChipsQueryKey: () => ["chips"],
  useCreateChip: () => ({ mutate: mocks.mutate, isPending: false }),
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
        data: { chip_id: "chip-01", size: 64, topology_id: "grid-64" },
      }),
    );
  });
});
