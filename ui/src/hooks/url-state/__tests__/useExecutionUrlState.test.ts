import { describe, it, expect, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { withNuqsTestingAdapter, type UrlUpdateEvent } from "nuqs/adapters/testing";

import { useExecutionUrlState } from "../useExecutionUrlState";

describe("useExecutionUrlState", () => {
  it("returns null default (not empty string) when no URL params are set", () => {
    const { result } = renderHook(() => useExecutionUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "" }),
    });

    expect(result.current.selectedChip).toBeNull();
  });

  it("reads initial chip from URL params", () => {
    const { result } = renderHook(() => useExecutionUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "chip=CHIP01" }),
    });

    expect(result.current.selectedChip).toBe("CHIP01");
  });

  it("setSelectedChip updates chip value", () => {
    const { result } = renderHook(() => useExecutionUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "" }),
    });

    act(() => {
      result.current.setSelectedChip("CHIP02");
    });

    expect(result.current.selectedChip).toBe("CHIP02");
  });

  it("setSelectedChip with null removes param from URL", () => {
    const { result } = renderHook(() => useExecutionUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "chip=CHIP01" }),
    });

    act(() => {
      result.current.setSelectedChip(null);
    });

    expect(result.current.selectedChip).toBeNull();
  });

  it("setSelectedChip with empty string removes param from URL", () => {
    const { result } = renderHook(() => useExecutionUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "chip=CHIP01" }),
    });

    act(() => {
      result.current.setSelectedChip("");
    });

    // Empty string is converted to null by the hook (chip || null)
    expect(result.current.selectedChip).toBeNull();
  });

  it("isInitialized becomes true after mount", () => {
    const { result } = renderHook(() => useExecutionUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "" }),
    });

    expect(result.current.isInitialized).toBe(true);
  });
});

describe("useExecutionUrlState list view", () => {
  const last = (onUrlUpdate: ReturnType<typeof vi.fn<(event: UrlUpdateEvent) => void>>) =>
    onUrlUpdate.mock.calls[onUrlUpdate.mock.calls.length - 1]?.[0];

  function setup(searchParams: string) {
    const onUrlUpdate = vi.fn<(event: UrlUpdateEvent) => void>();
    const hook = renderHook(() => useExecutionUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams, onUrlUpdate, hasMemory: true }),
    });
    return { ...hook, onUrlUpdate };
  }

  it("opens an old link as the grouped latest runs on the first page", () => {
    expect(setup("chip=CHIP01").result.current).toMatchObject({
      selectedChip: "CHIP01",
      selectedDate: "latest",
      groupSessions: true,
      page: 1,
    });
  });

  it("restores a day, the flat list and the page", () => {
    expect(setup("chip=CHIP01&date=20261120&flat=true&page=2").result.current).toMatchObject({
      selectedDate: "20261120",
      groupSessions: false,
      page: 2,
    });
  });

  it.each(["date=20261301", "date=2026-11-20", "date=latest", "flat=yes", "page=0", "page=x"])(
    "reads %j as the default",
    (search) => {
      expect(setup(search).result.current).toMatchObject({
        selectedDate: "latest",
        groupSessions: true,
        page: 1,
      });
    },
  );

  it("adds a history entry per change and returns to the first page", async () => {
    const { result, onUrlUpdate } = setup("chip=CHIP01&date=20261120&page=3");

    act(() => result.current.changeGrouping(false));
    await waitFor(() =>
      expect(last(onUrlUpdate)).toMatchObject({
        queryString: "?chip=CHIP01&date=20261120&flat=true",
        options: { history: "push" },
      }),
    );

    act(() => result.current.changeDate("latest"));
    await waitFor(() => expect(last(onUrlUpdate)?.queryString).toBe("?chip=CHIP01&flat=true"));

    act(() => result.current.setPage(2));
    await waitFor(() =>
      expect(last(onUrlUpdate)?.queryString).toBe("?chip=CHIP01&flat=true&page=2"),
    );

    // Another chip has its own days: the day and page reset, the grouping stays.
    act(() => result.current.changeDate("20261120"));
    act(() => result.current.changeChip("CHIP02"));
    await waitFor(() =>
      expect(last(onUrlUpdate)).toMatchObject({
        queryString: "?chip=CHIP02&flat=true",
        options: { history: "push" },
      }),
    );
  });

  it("replaces the URL when the default chip is set or the project changes", async () => {
    const { result, onUrlUpdate } = setup("date=20261120&page=2");

    act(() => result.current.setSelectedChip("CHIP01"));
    await waitFor(() =>
      expect(last(onUrlUpdate)).toMatchObject({
        queryString: "?date=20261120&page=2&chip=CHIP01",
        options: { history: "replace" },
      }),
    );

    act(() => result.current.resetForProject("CHIP02"));
    await waitFor(() =>
      expect(last(onUrlUpdate)).toMatchObject({
        queryString: "?chip=CHIP02",
        options: { history: "replace" },
      }),
    );
  });
});
