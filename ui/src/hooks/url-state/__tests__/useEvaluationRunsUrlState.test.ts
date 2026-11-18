import { act, renderHook, waitFor } from "@testing-library/react";
import { withNuqsTestingAdapter, type UrlUpdateEvent } from "nuqs/adapters/testing";
import { describe, expect, it, vi } from "vitest";

import { useEvaluationRunsUrlState } from "../useEvaluationRunsUrlState";

const last = <T>(items: readonly T[]): T | undefined => items[items.length - 1];

const lastUpdate = (onUrlUpdate: ReturnType<typeof vi.fn<(event: UrlUpdateEvent) => void>>) =>
  last(onUrlUpdate.mock.calls)?.[0];

function setup(searchParams: string) {
  const onUrlUpdate = vi.fn<(event: UrlUpdateEvent) => void>();
  const hook = renderHook(() => useEvaluationRunsUrlState(), {
    wrapper: withNuqsTestingAdapter({ searchParams, onUrlUpdate, hasMemory: true }),
  });
  return { ...hook, onUrlUpdate };
}

describe("useEvaluationRunsUrlState", () => {
  it("restores chip, task and page from the URL", () => {
    const { result } = setup("chip=64Qv1&task=CheckT1&page=3");
    expect(result.current).toMatchObject({ chipId: "64Qv1", taskName: "CheckT1", page: 3 });
  });

  it.each(["", "page=abc", "page=0", "page=-2"])("reads %j as the first page", (search) => {
    expect(setup(search).result.current.page).toBe(1);
  });

  it("returns to the first page when a filter changes, adding a history entry", async () => {
    const { result, onUrlUpdate } = setup("chip=64Qv1&page=3");
    act(() => result.current.setTaskName("CheckRabi"));

    expect(result.current).toMatchObject({ chipId: "64Qv1", taskName: "CheckRabi", page: 1 });
    await waitFor(() =>
      expect(lastUpdate(onUrlUpdate)).toMatchObject({
        queryString: "?chip=64Qv1&task=CheckRabi",
        options: { history: "push" },
      }),
    );

    act(() => result.current.setChipId(""));
    await waitFor(() => expect(lastUpdate(onUrlUpdate)?.queryString).toBe("?task=CheckRabi"));
  });

  it("pushes page changes and replaces corrections", async () => {
    const { result, onUrlUpdate } = setup("page=2");
    act(() => result.current.setPage(3));
    await waitFor(() =>
      expect(lastUpdate(onUrlUpdate)).toMatchObject({
        queryString: "?page=3",
        options: { history: "push" },
      }),
    );

    act(() => result.current.setPage(1, { replace: true }));
    expect(result.current.page).toBe(1);
    await waitFor(() =>
      expect(lastUpdate(onUrlUpdate)).toMatchObject({
        queryString: "",
        options: { history: "replace" },
      }),
    );
  });
});
