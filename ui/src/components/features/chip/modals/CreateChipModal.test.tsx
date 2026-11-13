import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CreateChipModal } from "@/components/features/chip/modals/CreateChipModal";

const FAKE_PRESET = {
  preset_id: "fake",
  name: "Virtual fake device",
  description: "64 simulated qubits on 16 MUXes.",
  topology_id: "square-lattice-mux-64",
  n_qubits: 64,
  mux_count: 16,
  workflow_template_id: "fake_calibration",
};

const mocks = vi.hoisted(() => ({
  mutate: vi.fn(),
  push: vi.fn(),
  toastSuccess: vi.fn(),
  mutationOptions: undefined as
    | { onSuccess: (data: unknown) => void; onError: (err: Error) => void }
    | undefined,
  isLoadingSources: false,
  isConfigSourcesError: false,
  configSources: {
    available: true,
    sources: [
      {
        system_id: "64Qv3",
        backend: "quel1",
        mux_count: 16,
        files: ["box.yaml"],
      },
    ],
    presets: [] as unknown[],
    deployment_backend: "qubex" as string | undefined,
  },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.push }),
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock("@/client/chip/chip", () => ({
  getListChipsQueryKey: () => ["chips"],
  useCreateChip: (options: { mutation: typeof mocks.mutationOptions }) => {
    mocks.mutationOptions = options.mutation;
    return { mutate: mocks.mutate, isPending: false };
  },
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
  useToast: () => ({ success: mocks.toastSuccess, info: vi.fn() }),
}));

vi.mock("@/client/topology/topology", () => ({
  useListTopologies: () => ({
    isLoading: false,
    data: {
      data: {
        topologies: [
          { id: "grid-64", name: "64-qubit grid", num_qubits: 64 },
          {
            id: "square-lattice-mux-16",
            name: "16-qubit lattice",
            num_qubits: 16,
          },
          {
            id: "square-lattice-mux-64",
            name: "Square Lattice with MUX",
            num_qubits: 64,
          },
        ],
      },
    },
  }),
}));

describe("CreateChipModal", () => {
  afterEach(() => {
    cleanup();
    mocks.mutate.mockReset();
    mocks.push.mockReset();
    mocks.toastSuccess.mockReset();
    mocks.configSources.available = true;
    mocks.configSources.presets = [];
    mocks.configSources.deployment_backend = "qubex";
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
    // The deployment may be fake, so no hardware setting is offered yet.
    expect(screen.queryByLabelText("Topology Template")).toBeNull();
    expect(screen.queryByLabelText("Wiring")).toBeNull();
    expect(screen.getByText("Checking the deployment...")).toBeTruthy();
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
      "Unable to check how this deployment creates chips",
    );
    expect(screen.queryByText(/No Qubex configuration tree is mounted/)).toBeNull();
    expect(screen.queryByLabelText("Topology Template")).toBeNull();
    expect(screen.queryByText(/Virtual device/)).toBeNull();
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
    fireEvent.change(screen.getByLabelText("Backend"), {
      target: { value: "quel3" },
    });
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
    fireEvent.change(screen.getByLabelText("Wiring"), {
      target: { value: "64Qv3" },
    });
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
        data: {
          chip_id: "64Qv4",
          size: 64,
          topology_id: "grid-64",
          config: { create: false },
        },
      }),
    );
  });

  it("explains when no configuration tree is mounted", async () => {
    mocks.configSources.available = false;
    render(<CreateChipModal isOpen onClose={vi.fn()} />);

    expect(screen.getByText(/No Qubex configuration tree is mounted/)).toBeTruthy();
    expect(screen.queryByLabelText("Wiring")).toBeNull();
  });

  it("keeps the hardware form unless the deployment is fake", () => {
    render(<CreateChipModal isOpen onClose={vi.fn()} />);

    expect(screen.getByLabelText("Topology Template")).toBeTruthy();
    expect(screen.queryByText("Fake backend")).toBeNull();
    expect(screen.queryByRole("radio")).toBeNull();
  });

  describe("on a fake deployment", () => {
    function fakeDeployment() {
      mocks.configSources.deployment_backend = "fake";
      mocks.configSources.presets = [FAKE_PRESET];
    }

    it("creates the fixed 64-qubit virtual chip from the chip ID alone", async () => {
      fakeDeployment();
      render(<CreateChipModal isOpen onClose={vi.fn()} />);

      // No hardware choice, topology picker, wiring or backend control
      expect(screen.queryByRole("radio")).toBeNull();
      expect(screen.queryByRole("combobox")).toBeNull();
      expect(screen.queryByLabelText("Topology Template")).toBeNull();
      expect(screen.queryByLabelText("Wiring")).toBeNull();
      expect(screen.queryByRole("checkbox")).toBeNull();
      // The fixed device is shown as information
      expect(screen.getByText("Fake backend")).toBeTruthy();
      expect(screen.getByTestId("fake-device-topology")).toHaveTextContent(
        "Square Lattice with MUX square-lattice-mux-64",
      );
      expect(screen.getByText("64 qubits, 16 MUX")).toBeTruthy();
      expect(screen.getByText(/Fake Backend Calibration/)).toBeTruthy();

      fireEvent.change(screen.getByPlaceholderText("e.g., 64Q, Chip001"), {
        target: { value: " fake-64q " },
      });
      fireEvent.click(screen.getByRole("button", { name: "Create Chip" }));
      await waitFor(() =>
        expect(mocks.mutate).toHaveBeenCalledWith({
          data: {
            chip_id: "fake-64q",
            size: 64,
            topology_id: "square-lattice-mux-64",
            config: { preset: "fake" },
          },
        }),
      );
    });

    it("wraps a long chip ID in the generated directory name", () => {
      fakeDeployment();
      render(<CreateChipModal isOpen onClose={vi.fn()} />);
      const longId = "fake-chip-with-a-very-long-identifier-that-must-wrap-0123456789";
      fireEvent.change(screen.getByPlaceholderText("e.g., 64Q, Chip001"), {
        target: { value: longId },
      });

      const directory = screen.getByText(`${longId}/`);
      expect(directory.tagName).toBe("CODE");
      expect(directory).toHaveClass("break-all");
      expect(directory.closest("fieldset")).toHaveClass("min-w-0");
      expect(directory.closest(".label")).toBeNull();
    });

    it("blocks creation when no configuration tree is mounted", async () => {
      fakeDeployment();
      mocks.configSources.available = false;
      render(<CreateChipModal isOpen onClose={vi.fn()} />);
      const input = screen.getByPlaceholderText("e.g., 64Q, Chip001");
      fireEvent.change(input, { target: { value: "fake-64q" } });

      expect(screen.getByRole("alert")).toHaveTextContent(
        "the virtual configuration cannot be generated",
      );
      expect(screen.queryByLabelText("Topology Template")).toBeNull();
      expect(screen.queryByText(/only the chip record is created/)).toBeNull();
      expect(screen.getByRole("button", { name: "Create Chip" })).toBeDisabled();
      await act(async () => {
        fireEvent.submit(input.closest("form")!);
      });
      expect(mocks.mutate).not.toHaveBeenCalled();
    });

    it("blocks creation when the API does not offer the virtual device", async () => {
      mocks.configSources.deployment_backend = "fake";
      render(<CreateChipModal isOpen onClose={vi.fn()} />);
      const input = screen.getByPlaceholderText("e.g., 64Q, Chip001");
      fireEvent.change(input, { target: { value: "fake-64q" } });

      expect(screen.getByRole("alert")).toHaveTextContent("runs the fake backend");
      expect(screen.queryByLabelText("Topology Template")).toBeNull();
      expect(screen.getByRole("button", { name: "Create Chip" })).toBeDisabled();
      await act(async () => {
        fireEvent.submit(input.closest("form")!);
      });
      expect(mocks.mutate).not.toHaveBeenCalled();
    });

    it("offers the fake calibration template for the created chip", () => {
      fakeDeployment();
      const onSuccess = vi.fn();
      render(<CreateChipModal isOpen onClose={vi.fn()} onSuccess={onSuccess} />);
      const config = {
        status: "created",
        path: "fake-64q",
        preset: "fake",
        files: [],
        message: "Created fake-64q/ for the virtual 64-qubit, 16-MUX fake device.",
      };

      act(() =>
        mocks.mutationOptions?.onSuccess({
          data: { chip_id: "fake-64q", config },
        }),
      );

      expect(onSuccess).toHaveBeenCalledWith("fake-64q", config, undefined);
      const [message, options] = mocks.toastSuccess.mock.calls[0];
      expect(message).toBe(config.message);
      expect(options.action.label).toBe("Open template");
      options.action.onClick();
      expect(mocks.push).toHaveBeenCalledWith(
        "/workflow/new?backend=fake&template=fake_calibration&chip_id=fake-64q",
      );
    });

    it("leaves the next step to the first calibration guide when it adopts the chip", () => {
      fakeDeployment();
      render(<CreateChipModal isOpen onClose={vi.fn()} guidedByJourney />);
      const config = {
        status: "created",
        path: "fake-64q",
        preset: "fake",
        files: [],
        message: "Created fake-64q/ for the virtual 64-qubit, 16-MUX fake device.",
      };

      act(() =>
        mocks.mutationOptions?.onSuccess({
          data: { chip_id: "fake-64q", config },
        }),
      );

      // The message stays; its shortcut, which would open the editor outside the guide, does not.
      expect(mocks.toastSuccess).toHaveBeenCalledWith(config.message, undefined);
    });
  });
});
