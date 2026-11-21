import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { MetricScriptResponse } from "@/schemas";

import { useMetricScriptDocument } from "../useMetricScriptDocument";
import { scriptResponse, SOURCE } from "./scriptFixtures";

const mocks = vi.hoisted(() => ({
  script: null as unknown,
  refetch: vi.fn(),
  mutateAsync: vi.fn(),
  toast: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}));

vi.mock("@/client/metric-script/metric-script", () => ({
  getGetMetricScriptQueryKey: (id: string) => [`/metric-scripts/${id}`],
  getListMetricScriptsQueryKey: () => ["/metric-scripts"],
  useGetMetricScript: () => ({
    data: mocks.script ? { data: mocks.script } : undefined,
    isLoading: false,
    error: null,
    refetch: mocks.refetch,
  }),
  useUpdateMetricScript: () => ({ mutateAsync: mocks.mutateAsync, isPending: false }),
}));

vi.mock("@/components/ui/Toast", () => ({ useToast: () => mocks.toast }));

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

function renderDocument() {
  return renderHook(() => useMetricScriptDocument("ms_000000000001"), { wrapper });
}

describe("useMetricScriptDocument", () => {
  beforeEach(() => {
    mocks.script = scriptResponse();
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("loads the script into a clean draft and tracks code and settings changes", async () => {
    const { result } = renderDocument();
    await waitFor(() => expect(result.current.isReady).toBe(true));

    expect(result.current.code).toBe(SOURCE);
    expect(result.current.settings).toEqual({
      name: "Coherence",
      description: "T1 per qubit",
      visibility: "private",
    });
    expect(result.current.isDirty).toBe(false);

    act(() => result.current.setCode(`${SOURCE}\n# note\n`));
    expect(result.current.isDirty).toBe(true);
    act(() => result.current.setCode(SOURCE));
    expect(result.current.isDirty).toBe(false);
    act(() => result.current.setSettings({ visibility: "project" }));
    expect(result.current.isDirty).toBe(true);
  });

  it("saves with the opened revision and adopts the saved script", async () => {
    const saved = scriptResponse({ revision: 4, active_revision: 4, source: `${SOURCE}# v4\n` });
    mocks.mutateAsync.mockResolvedValue({ data: saved });
    const { result } = renderDocument();
    await waitFor(() => expect(result.current.isReady).toBe(true));

    act(() => result.current.setCode(`${SOURCE}# v4\n`));
    let response: MetricScriptResponse | null = null;
    await act(async () => {
      response = await result.current.save();
    });

    expect(response).toBe(saved);
    expect(mocks.mutateAsync).toHaveBeenCalledWith({
      scriptId: "ms_000000000001",
      data: {
        name: "Coherence",
        description: "T1 per qubit",
        visibility: "private",
        source: `${SOURCE}# v4\n`,
        expected_revision: 3,
      },
    });
    expect(result.current.isDirty).toBe(false);
    expect(mocks.toast.success).toHaveBeenCalledWith("Saved r4");
  });

  it("does not send unchanged source and warns when the saved text is invalid", async () => {
    mocks.mutateAsync.mockResolvedValue({
      data: scriptResponse({ revision: 4, status: "invalid", active_revision: 3 }),
    });
    const { result } = renderDocument();
    await waitFor(() => expect(result.current.isReady).toBe(true));

    act(() => result.current.setSettings({ name: "Renamed" }));
    await act(async () => {
      await result.current.save();
    });

    expect(mocks.mutateAsync.mock.calls[0][0].data).not.toHaveProperty("source");
    expect(mocks.toast.warning).toHaveBeenCalledWith("Saved r4 with errors; r3 stays active");
  });

  it("keeps the draft on a conflict, moves the baseline and offers the saved version", async () => {
    const elsewhere = scriptResponse({ revision: 5, active_revision: 5, source: "# other\n" });
    mocks.mutateAsync.mockRejectedValueOnce({
      response: {
        status: 409,
        data: {
          detail: "Script was saved as revision 5 since revision 3; reload it before saving",
        },
      },
    });
    mocks.refetch.mockResolvedValue({ data: { data: elsewhere } });
    const { result } = renderDocument();
    await waitFor(() => expect(result.current.isReady).toBe(true));

    act(() => result.current.setCode("# mine\n"));
    let response: MetricScriptResponse | null = scriptResponse();
    await act(async () => {
      response = await result.current.save();
    });

    expect(response).toBeNull();
    expect(result.current.code).toBe("# mine\n");
    expect(result.current.isDirty).toBe(true);
    expect(mocks.toast.error).toHaveBeenCalledWith(
      "This script was saved elsewhere",
      expect.objectContaining({ action: expect.objectContaining({ label: "Load saved version" }) }),
    );

    // The next save is checked against the version saved elsewhere.
    mocks.mutateAsync.mockResolvedValueOnce({ data: scriptResponse({ revision: 6 }) });
    await act(async () => {
      await result.current.save();
    });
    expect(mocks.mutateAsync.mock.calls[1][0].data.expected_revision).toBe(5);

    // Loading the saved version drops the draft.
    const action = mocks.toast.error.mock.calls[0][1].action as { onClick: () => void };
    await act(async () => {
      action.onClick();
    });
    await waitFor(() => expect(result.current.code).toBe("# other\n"));
  });
});
