import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GlobalExecutionIndicator } from "@/components/layout/GlobalExecutionIndicator";

const push = vi.fn();
const success = vi.fn();
const error = vi.fn();
const info = vi.fn();
const warning = vi.fn();

let lockStatus: {
  lock: boolean;
  execution_id?: string;
  chip_id?: string;
  name?: string;
  status?: string;
} = { lock: false };

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

vi.mock("@/client/execution/execution", () => ({
  useGetExecutionLockStatus: () => ({ data: { data: lockStatus } }),
}));

vi.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ success, error, info, warning }),
}));

describe("GlobalExecutionIndicator", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    lockStatus = { lock: false };
  });

  it("shows Running while the lock is held by a running execution", () => {
    lockStatus = {
      lock: true,
      execution_id: "exec-1",
      chip_id: "chip-1",
      name: "Calibration run",
      status: "running",
    };
    render(<GlobalExecutionIndicator />);

    expect(screen.getByText("Running")).toBeTruthy();
    expect(screen.queryByText("Cancelling")).toBeNull();
  });

  it("shows Cancelling while the lock is held by a cancelling execution", () => {
    lockStatus = {
      lock: true,
      execution_id: "exec-1",
      chip_id: "chip-1",
      name: "Calibration run",
      status: "cancelling",
    };
    render(<GlobalExecutionIndicator />);

    expect(screen.getByText("Cancelling")).toBeTruthy();
    expect(screen.queryByText("Running")).toBeNull();
  });

  it("renders nothing when no execution lock is held", () => {
    lockStatus = { lock: false };
    const { container } = render(<GlobalExecutionIndicator />);

    expect(container.firstChild).toBeNull();
  });
});
