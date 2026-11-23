import type { ReactNode } from "react";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useFlowExecutionPlan } from "../useFlowExecutionPlan";

const mocks = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock("@/client/flow/flow", () => ({ getFlowExecutionPlan: mocks.get }));
vi.mock("@/contexts/ProjectContext", () => ({ useProject: () => ({ projectId: "p" }) }));

const VERSION = "2026-11-01T00:00:00";

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const plan = (chip: string, version = VERSION) => ({
  data: { flow_name: "f", chip_id: chip, source_updated_at: version, status: "resolved" },
});

beforeEach(() => mocks.get.mockReset());
afterEach(cleanup);

describe("useFlowExecutionPlan", () => {
  it("never shows a response for an earlier chip", async () => {
    let release!: (value: unknown) => void;
    mocks.get.mockImplementationOnce(() => new Promise((resolve) => (release = resolve)));
    mocks.get.mockResolvedValueOnce(plan("chip-2"));
    const { result, rerender } = renderHook(
      ({ chipId }) =>
        useFlowExecutionPlan({ flowName: "f", chipId, sourceVersion: VERSION, enabled: true }),
      { initialProps: { chipId: "chip-1" }, wrapper },
    );
    expect(result.current.status).toBe("loading");
    rerender({ chipId: "chip-2" });
    release(plan("chip-1"));
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.status === "ready" && result.current.plan.chip_id).toBe("chip-2");
    expect(mocks.get).toHaveBeenLastCalledWith(
      "f",
      { chip_id: "chip-2" },
      undefined,
      expect.anything(),
    );
  });

  it("reports a plan of another saved version as stale", async () => {
    mocks.get.mockResolvedValueOnce(plan("chip-1", "2026-11-02T00:00:00"));
    const { result } = renderHook(
      () =>
        useFlowExecutionPlan({
          flowName: "f",
          chipId: "chip-1",
          sourceVersion: VERSION,
          enabled: true,
        }),
      { wrapper },
    );
    await waitFor(() => expect(result.current.status).toBe("stale"));
  });

  it("does not fetch while closed and reports errors", async () => {
    const { result, rerender } = renderHook(
      ({ enabled }) =>
        useFlowExecutionPlan({ flowName: "f", chipId: "chip-1", sourceVersion: VERSION, enabled }),
      { initialProps: { enabled: false }, wrapper },
    );
    expect(mocks.get).not.toHaveBeenCalled();
    mocks.get.mockRejectedValueOnce(new Error("boom"));
    rerender({ enabled: true });
    await waitFor(() => expect(result.current.status).toBe("error"));
  });
});
