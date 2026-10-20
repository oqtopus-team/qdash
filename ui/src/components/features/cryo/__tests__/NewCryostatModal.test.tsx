import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NewCryostatModal } from "@/components/features/cryo/CryoPageContent";

const mocks = vi.hoisted(() => ({ mutateAsync: vi.fn() }));

vi.mock("@tanstack/react-query", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@tanstack/react-query")>()),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock("@/client/chip/chip", () => ({
  useListChips: () => ({ data: undefined }),
}));

vi.mock("@/client/cooldown/cooldown", () => ({
  getListCooldownsQueryKey: () => ["cooldowns"],
  useCreateCooldown: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useListCooldowns: () => ({ data: undefined }),
}));

vi.mock("@/client/cryostat/cryostat", () => ({
  getListCryostatsQueryKey: () => ["cryostats"],
  useCreateCryostat: () => ({
    mutateAsync: mocks.mutateAsync,
    isPending: false,
  }),
  useListCryostats: () => ({ data: undefined }),
}));

vi.mock("@/components/features/cryo/CryostatCard", () => ({
  CryostatCard: () => null,
}));

/** Clicks the submit button of the modal. */
function submit() {
  fireEvent.click(screen.getByRole("button", { name: "Create cryostat" }));
}

describe("NewCryostatModal", () => {
  afterEach(() => {
    cleanup();
    mocks.mutateAsync.mockReset();
  });

  it("shows an inline error for an empty cryo ID", async () => {
    render(<NewCryostatModal onClose={vi.fn()} onCreated={vi.fn()} />);
    submit();

    const error = await screen.findByText("Cryo ID is required");
    const input = screen.getByLabelText(/Cryo ID/);
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(input.getAttribute("aria-describedby")).toBe(error.id);
    expect(mocks.mutateAsync).not.toHaveBeenCalled();
  });

  it("rejects a whitespace-only cryo ID", async () => {
    render(<NewCryostatModal onClose={vi.fn()} onCreated={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/Cryo ID/), {
      target: { value: "   " },
    });
    submit();

    expect(await screen.findByText("Cryo ID is required")).toBeTruthy();
    expect(screen.getByLabelText(/Cryo ID/).getAttribute("aria-invalid")).toBe("true");
    expect(mocks.mutateAsync).not.toHaveBeenCalled();
  });

  it("rejects a cryo ID longer than 100 characters", async () => {
    render(<NewCryostatModal onClose={vi.fn()} onCreated={vi.fn()} />);
    fireEvent.change(screen.getByLabelText(/Cryo ID/), {
      target: { value: "a".repeat(101) },
    });
    submit();

    expect(await screen.findByText("Cryo ID must be 100 characters or fewer")).toBeTruthy();
    expect(mocks.mutateAsync).not.toHaveBeenCalled();
  });

  it("submits trimmed values and closes on success", async () => {
    mocks.mutateAsync.mockResolvedValue({});
    const onClose = vi.fn();
    const onCreated = vi.fn();
    render(<NewCryostatModal onClose={onClose} onCreated={onCreated} />);
    fireEvent.change(screen.getByLabelText(/Cryo ID/), {
      target: { value: "  K-101  " },
    });
    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "  Triton XL  " },
    });
    fireEvent.change(screen.getByLabelText("Manufacturer"), {
      target: { value: " Oxford " },
    });
    fireEvent.change(screen.getByLabelText("Model"), {
      target: { value: " Triton 200 " },
    });
    fireEvent.change(screen.getByLabelText("Location"), {
      target: { value: " Lab B-204 " },
    });
    submit();

    await waitFor(() =>
      expect(mocks.mutateAsync).toHaveBeenCalledWith({
        data: {
          cryo_id: "K-101",
          name: "Triton XL",
          location: "Lab B-204",
          manufacturer: "Oxford",
          model: "Triton 200",
          status: "active",
        },
      }),
    );
    await waitFor(() => expect(onCreated).toHaveBeenCalled());
    expect(onClose).toHaveBeenCalled();
  });

  it("shows the server error and stays open when creation fails", async () => {
    mocks.mutateAsync.mockRejectedValue({
      response: { data: { detail: "Cryostat already exists" } },
    });
    const onClose = vi.fn();
    const onCreated = vi.fn();
    render(<NewCryostatModal onClose={onClose} onCreated={onCreated} />);
    fireEvent.change(screen.getByLabelText(/Cryo ID/), {
      target: { value: "K-101" },
    });
    submit();

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Cryostat already exists");
    expect(onClose).not.toHaveBeenCalled();
    expect(onCreated).not.toHaveBeenCalled();
  });
});
