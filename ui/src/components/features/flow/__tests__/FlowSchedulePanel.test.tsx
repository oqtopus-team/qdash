import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FlowSchedulePanel } from "../FlowSchedulePanel";

const mocks = vi.hoisted(() => ({
  scheduleFlow: vi.fn(),
  listFlowSchedules: vi.fn(),
  deleteFlowSchedule: vi.fn(),
  updateFlowSchedule: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("@/client/flow/flow", () => ({
  scheduleFlow: mocks.scheduleFlow,
  listFlowSchedules: mocks.listFlowSchedules,
  deleteFlowSchedule: mocks.deleteFlowSchedule,
  updateFlowSchedule: mocks.updateFlowSchedule,
}));

vi.mock("@/components/ui/Toast", () => ({ useToast: () => mocks.toast }));

const existingCronSchedule = {
  schedule_id: "schedule-1",
  flow_name: "my-flow",
  schedule_type: "cron",
  cron: "0 2 * * *",
  next_run: null,
  active: true,
  created_at: "2026-11-01T00:00:00Z",
};

/** Renders the schedule panel inside a fresh query client. */
function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <FlowSchedulePanel flowName="my-flow" />
    </QueryClientProvider>,
  );
}

/** Switches the panel to the one-time schedule form. */
function selectOneTime() {
  fireEvent.click(screen.getByRole("button", { name: "One-time" }));
}

describe("FlowSchedulePanel schedule form", () => {
  beforeEach(() => {
    mocks.listFlowSchedules.mockResolvedValue({ data: { schedules: [existingCronSchedule] } });
    mocks.scheduleFlow.mockResolvedValue({ data: {} });
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("requires a cron expression", async () => {
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Add Cron Schedule" }));

    const error = await screen.findByText("Please enter a cron expression");
    const input = screen.getByLabelText("Cron Expression");
    expect(error.id).toBe("schedule-cron-error");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAttribute("aria-describedby", "schedule-cron-error");
    expect(mocks.scheduleFlow).not.toHaveBeenCalled();
    expect(mocks.toast.error).not.toHaveBeenCalled();
  });

  it("reports a duplicate cron expression as a field error", async () => {
    renderPanel();
    expect(await screen.findByRole("button", { name: "Delete schedule" })).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Cron Expression"), {
      target: { value: "  0 2 * * *  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add Cron Schedule" }));

    expect(await screen.findByText("This cron schedule already exists")).toBeTruthy();
    expect(screen.getByLabelText("Cron Expression")).toHaveAttribute("aria-invalid", "true");
    expect(mocks.scheduleFlow).not.toHaveBeenCalled();
    expect(mocks.toast.error).not.toHaveBeenCalled();
  });

  it("submits a trimmed cron schedule and clears the expression", async () => {
    renderPanel();
    fireEvent.change(screen.getByLabelText("Cron Expression"), {
      target: { value: "  0 3 * * *  " },
    });
    fireEvent.click(screen.getByRole("checkbox", { name: "Enable schedule immediately" }));
    fireEvent.click(screen.getByRole("button", { name: "Add Cron Schedule" }));

    await waitFor(() =>
      expect(mocks.scheduleFlow).toHaveBeenCalledWith("my-flow", {
        cron: "0 3 * * *",
        active: false,
        parameters: {},
      }),
    );
    await waitFor(() =>
      expect(mocks.toast.success).toHaveBeenCalledWith("Schedule created successfully!"),
    );
    expect(screen.getByLabelText("Cron Expression")).toHaveValue("");
  });

  it("submits a cron schedule as active by default", async () => {
    renderPanel();
    fireEvent.change(screen.getByLabelText("Cron Expression"), {
      target: { value: "0 4 * * *" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Add Cron Schedule" }));

    await waitFor(() =>
      expect(mocks.scheduleFlow).toHaveBeenCalledWith("my-flow", {
        cron: "0 4 * * *",
        active: true,
        parameters: {},
      }),
    );
  });

  it("does not show a field error after a successful create until the next submit", async () => {
    renderPanel();
    const input = screen.getByLabelText("Cron Expression");
    fireEvent.change(input, { target: { value: "0 5 * * *" } });
    fireEvent.click(screen.getByRole("button", { name: "Add Cron Schedule" }));
    await waitFor(() =>
      expect(mocks.toast.success).toHaveBeenCalledWith("Schedule created successfully!"),
    );
    await waitFor(() => expect(input).toHaveValue(""));

    fireEvent.change(input, { target: { value: "0 6 * * *" } });
    fireEvent.change(input, { target: { value: "" } });
    await waitFor(() => expect(input).toHaveValue(""));
    expect(screen.queryByText("Please enter a cron expression")).toBeNull();
    expect(input).toHaveAttribute("aria-invalid", "false");

    fireEvent.click(screen.getByRole("button", { name: "Add Cron Schedule" }));
    expect(await screen.findByText("Please enter a cron expression")).toBeTruthy();
    expect(mocks.scheduleFlow).toHaveBeenCalledTimes(1);
  });

  it("clears the other schedule type's error and ignores an empty cron for a one-time submit", async () => {
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: "Add Cron Schedule" }));
    expect(await screen.findByText("Please enter a cron expression")).toBeTruthy();

    selectOneTime();
    fireEvent.click(screen.getByRole("button", { name: "Cron" }));
    expect(screen.queryByText("Please enter a cron expression")).toBeNull();

    selectOneTime();
    fireEvent.change(screen.getByLabelText("Date (JST)"), { target: { value: "2026-12-02" } });
    fireEvent.click(screen.getByRole("button", { name: "Create One-time Schedule" }));

    await waitFor(() =>
      expect(mocks.scheduleFlow).toHaveBeenCalledWith("my-flow", {
        scheduled_time: "2026-12-02T00:00",
        parameters: {},
      }),
    );
  });

  it("rejects a time whose date was cleared", async () => {
    renderPanel();
    selectOneTime();
    fireEvent.change(screen.getByRole("combobox", { name: "Hour (JST)" }), {
      target: { value: "09" },
    });
    fireEvent.change(screen.getByLabelText("Date (JST)"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Create One-time Schedule" }));

    expect(await screen.findByText("Please select a scheduled time")).toBeTruthy();
    expect(screen.getByLabelText("Date (JST)")).toHaveAttribute("aria-invalid", "true");
    expect(mocks.scheduleFlow).not.toHaveBeenCalled();
  });

  it("requires a scheduled time for a one-time schedule", async () => {
    renderPanel();
    selectOneTime();
    fireEvent.click(screen.getByRole("button", { name: "Create One-time Schedule" }));

    const error = await screen.findByText("Please select a scheduled time");
    const dateInput = screen.getByLabelText("Date (JST)");
    expect(error.id).toBe("schedule-time-error");
    expect(dateInput).toHaveAttribute("aria-invalid", "true");
    expect(dateInput).toHaveAttribute("aria-describedby", "schedule-time-error");
    expect(mocks.scheduleFlow).not.toHaveBeenCalled();
    expect(mocks.toast.error).not.toHaveBeenCalled();
  });

  it("submits the JST date, hour and minute as the scheduled time", async () => {
    renderPanel();
    selectOneTime();
    fireEvent.change(screen.getByLabelText("Date (JST)"), { target: { value: "2026-12-01" } });
    fireEvent.change(screen.getByRole("combobox", { name: "Hour (JST)" }), {
      target: { value: "09" },
    });
    fireEvent.change(screen.getByRole("combobox", { name: "Minute (JST)" }), {
      target: { value: "35" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create One-time Schedule" }));

    await waitFor(() =>
      expect(mocks.scheduleFlow).toHaveBeenCalledWith("my-flow", {
        scheduled_time: "2026-12-01T09:35",
        parameters: {},
      }),
    );
  });

  it("uses the current JST date when only the time is chosen", async () => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(new Date("2026-11-10T16:30:00Z"));
    renderPanel();
    selectOneTime();
    fireEvent.change(screen.getByRole("combobox", { name: "Hour (JST)" }), {
      target: { value: "07" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create One-time Schedule" }));

    await waitFor(() =>
      expect(mocks.scheduleFlow).toHaveBeenCalledWith("my-flow", {
        scheduled_time: "2026-11-11T07:00",
        parameters: {},
      }),
    );
  });

  it("keeps an API failure as a submission error", async () => {
    mocks.scheduleFlow.mockRejectedValue(
      Object.assign(new Error("Request failed with status code 400"), {
        response: { data: { detail: "Invalid cron expression" } },
      }),
    );
    renderPanel();
    fireEvent.change(screen.getByLabelText("Cron Expression"), { target: { value: "bad" } });
    fireEvent.click(screen.getByRole("button", { name: "Add Cron Schedule" }));

    await waitFor(() =>
      expect(mocks.toast.error).toHaveBeenCalledWith(
        "Failed to create schedule: Invalid cron expression",
      ),
    );
    expect(screen.getByLabelText("Cron Expression")).toHaveAttribute("aria-invalid", "false");
  });
});
