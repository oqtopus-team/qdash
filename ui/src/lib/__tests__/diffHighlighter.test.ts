import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { disposeHighlighter, getSharedHighlighter, getHighlighterType } from "@pierre/diffs";
import { useDiffHighlighter } from "@/lib/diffHighlighter";

afterEach(async () => {
  cleanup();
  vi.restoreAllMocks();
  await disposeHighlighter();
});

it("recovers from theme resolution failure in the real cached Highlights instance", async () => {
  const instance = await getSharedHighlighter({
    themes: [],
    langs: [],
    preferredHighlighter: "highlights",
  });
  vi.spyOn(instance.themeResolver, "resolveThemes").mockRejectedValueOnce(
    new Error("theme load failed"),
  );
  vi.spyOn(console, "warn").mockImplementation(() => {});
  const { result } = renderHook(() => useDiffHighlighter());
  await waitFor(() => expect(result.current).toBe("shiki-js"));
  expect(instance.isDisposed).toBe(true);
  await getSharedHighlighter({
    themes: ["pierre-light"],
    langs: ["python"],
    preferredHighlighter: "shiki-js",
  });
  expect(getHighlighterType()).toBe("shiki-js");
});
