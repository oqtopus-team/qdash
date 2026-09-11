import type { ReactNode } from "react";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useExecutionAvailability } from "../useExecutionAvailability";

const mocks = vi.hoisted(() => ({ check: vi.fn(), project: "project-1" }));
vi.mock("@/client/execution/execution", () => ({ checkExecutionAvailability: mocks.check }));
vi.mock("@/contexts/ProjectContext", () => ({ useProject: () => ({ projectId: mocks.project }) }));

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, wrapper };
}

beforeEach(() => {
  mocks.project = "project-1";
  mocks.check.mockReset();
});
afterEach(cleanup);
const request = { parameters: { chip_id: "chip-1", qid: "0" } };

describe("useExecutionAvailability", () => {
  it("keeps new targets disabled until their own check completes", async () => {
    mocks.check.mockResolvedValueOnce({ data: { available: true } });
    const { wrapper } = setup();
    const { result, rerender } = renderHook(
      ({ qid }) => useExecutionAvailability({ parameters: { chip_id: "chip-1", qid } }),
      { initialProps: { qid: "0" }, wrapper },
    );
    expect(result.current.disabledReason).toMatch(/Checking/);
    expect(result.current.isConflict).toBe(false);
    await waitFor(() => expect(result.current.disabledReason).toBeNull());
    let resolve!: (value: unknown) => void;
    mocks.check.mockImplementationOnce(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    rerender({ qid: "4" });
    expect(result.current.disabledReason).toMatch(/Checking/);
    await act(async () => resolve({ data: { available: false, reason: "MUX is busy" } }));
    await waitFor(() => expect(result.current.disabledReason).toBe("MUX is busy"));
  });

  it("polls and enables the target after a conflicting run releases its claim", async () => {
    mocks.check
      .mockResolvedValueOnce({ data: { available: false, reason: "Hardware in use" } })
      .mockResolvedValue({ data: { available: true } });
    const { wrapper } = setup();
    const { result } = renderHook(() => useExecutionAvailability(request), { wrapper });
    await waitFor(() => expect(result.current.disabledReason).toBe("Hardware in use"));
    expect(result.current.isConflict).toBe(true);
    await waitFor(() => expect(result.current.disabledReason).toBeNull(), { timeout: 3500 });
    expect(result.current.isConflict).toBe(false);
  });

  it("disables on a failed refresh even if the last response was available", async () => {
    mocks.check.mockResolvedValueOnce({ data: { available: true } });
    const { wrapper } = setup();
    const { result } = renderHook(() => useExecutionAvailability(request), { wrapper });
    await waitFor(() => expect(result.current.disabledReason).toBeNull());
    mocks.check.mockRejectedValueOnce(new Error("offline"));
    await act(async () => {
      await result.current.refetch();
    });
    await waitFor(() => expect(result.current.disabledReason).toMatch(/Unable to check/));
    expect(result.current.isConflict).toBe(false);
  });

  it("does not reuse another project's availability", async () => {
    mocks.check.mockResolvedValueOnce({ data: { available: true } });
    const { wrapper } = setup();
    const { result, rerender } = renderHook(() => useExecutionAvailability(request), { wrapper });
    await waitFor(() => expect(result.current.disabledReason).toBeNull());
    mocks.project = "project-2";
    mocks.check.mockImplementationOnce(() => new Promise(() => {}));
    rerender();
    expect(result.current.disabledReason).toMatch(/Checking/);
  });
});
