import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CooldownItem } from "@/components/features/cryo/CooldownItem";

const mocks = vi.hoisted(() => ({ updateMutateAsync: vi.fn() }));

vi.mock("@/client/cooldown/cooldown", () => ({
  useUpdateCooldown: () => ({
    mutateAsync: mocks.updateMutateAsync,
    isPending: false,
  }),
  useDeleteCooldown: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useAssignChipToCooldown: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUnassignChipFromCooldown: () => ({
    mutateAsync: vi.fn(),
    isPending: false,
  }),
}));

vi.mock("@/components/features/cryo/CooldownWiringSection", () => ({
  CooldownWiringSection: () => null,
}));

const cooldown = {
  cooldown_id: "CD-001",
  cryo_id: "K-101",
  description: "",
  started_at: "2026-01-10T03:00:00Z",
  ended_at: "2026-01-20T14:59:00Z",
  chip_ids: [],
};

/** Renders an expanded cooldown and opens the date editor. */
function renderAndEditDates(onChange = vi.fn()) {
  render(
    <CooldownItem
      cooldown={cooldown}
      allChips={[]}
      expanded
      onToggle={vi.fn()}
      onChange={onChange}
    />,
  );
  fireEvent.click(screen.getByTitle("Edit dates"));
  return onChange;
}

/** Clicks the date form's save button. */
function save() {
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
}

describe("CooldownItem date form", () => {
  afterEach(() => {
    cleanup();
    mocks.updateMutateAsync.mockReset();
  });

  it("resets the fields from the cooldown when editing starts", () => {
    renderAndEditDates();

    expect((screen.getByLabelText("Started") as HTMLInputElement).value).toBe("2026-01-10");
    expect((screen.getByLabelText(/Ended/) as HTMLInputElement).value).toBe("2026-01-20");
  });

  it("discards draft values on cancel", () => {
    renderAndEditDates();
    fireEvent.change(screen.getByLabelText("Started"), {
      target: { value: "2025-12-01" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    fireEvent.click(screen.getByTitle("Edit dates"));

    expect((screen.getByLabelText("Started") as HTMLInputElement).value).toBe("2026-01-10");
  });

  it("requires a start date", async () => {
    renderAndEditDates();
    fireEvent.change(screen.getByLabelText("Started"), {
      target: { value: "" },
    });
    save();

    const error = await screen.findByText("Start date is required");
    const input = screen.getByLabelText("Started");
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(input.getAttribute("aria-describedby")).toBe(error.id);
    expect(mocks.updateMutateAsync).not.toHaveBeenCalled();
  });

  it("shows the date-order error next to the end date", async () => {
    renderAndEditDates();
    fireEvent.change(screen.getByLabelText(/Ended/), {
      target: { value: "2026-01-05" },
    });
    save();

    const error = await screen.findByText("End date must be on or after the start date");
    const input = screen.getByLabelText(/Ended/);
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(input.getAttribute("aria-describedby")).toBe(error.id);
    expect(mocks.updateMutateAsync).not.toHaveBeenCalled();
  });

  it("submits the converted dates and closes the editor on success", async () => {
    mocks.updateMutateAsync.mockResolvedValue({});
    const onChange = renderAndEditDates();
    fireEvent.change(screen.getByLabelText("Started"), {
      target: { value: "2026-02-01" },
    });
    fireEvent.change(screen.getByLabelText(/Ended/), {
      target: { value: "2026-02-03" },
    });
    save();

    await waitFor(() =>
      expect(mocks.updateMutateAsync).toHaveBeenCalledWith({
        cooldownId: "CD-001",
        data: {
          started_at: "2026-02-01T12:00:00+09:00",
          ended_at: "2026-02-03T23:59:00+09:00",
        },
      }),
    );
    await waitFor(() => expect(onChange).toHaveBeenCalled());
    expect(screen.queryByLabelText("Started")).toBeNull();
  });

  it("sends a null end date when the end date is cleared", async () => {
    mocks.updateMutateAsync.mockResolvedValue({});
    renderAndEditDates();
    fireEvent.change(screen.getByLabelText(/Ended/), { target: { value: "" } });
    save();

    await waitFor(() =>
      expect(mocks.updateMutateAsync).toHaveBeenCalledWith({
        cooldownId: "CD-001",
        data: { started_at: "2026-01-10T12:00:00+09:00", ended_at: null },
      }),
    );
  });

  it("shows the server error and keeps the editor open when saving fails", async () => {
    mocks.updateMutateAsync.mockRejectedValue({
      response: { data: { detail: "Cooldown overlaps another cooldown" } },
    });
    const onChange = renderAndEditDates();
    save();

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Cooldown overlaps another cooldown");
    expect(screen.getByLabelText("Started")).toBeTruthy();
    expect(onChange).not.toHaveBeenCalled();
  });
});
