import { act, cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const diffs = vi.hoisted(() => ({
  disposeHighlighter: vi.fn(() => Promise.resolve()),
  canUseWASM: vi.fn(() => true),
  preloadHighlighter: vi.fn((_options: unknown) => Promise.resolve()),
}));
vi.mock("@pierre/diffs", () => ({
  ...diffs,
  DEFAULT_THEMES: { dark: "pierre-dark", light: "pierre-light" },
}));

interface ViewerProps {
  oldFile: unknown;
  newFile: unknown;
  options: Record<string, unknown>;
}
const viewer = vi.hoisted(() => ({ renders: [] as ViewerProps[], mounts: 0 }));
vi.mock("@pierre/diffs/react", async () => {
  const { useEffect } = await import("react");
  return {
    MultiFileDiff: (props: ViewerProps) => {
      viewer.renders.push(props);
      useEffect(() => {
        viewer.mounts++;
      }, []);
      return <div data-testid="diff">{String(props.options.preferredHighlighter)}</div>;
    },
  };
});

const theme = vi.hoisted(() => ({ name: "light" }));
vi.mock("@/contexts/ThemeContext", () => ({
  useTheme: () => ({ theme: theme.name }),
}));

type ViewerModule = typeof import("../PierreDiffViewer");

async function freshViewer(): Promise<ViewerModule["PierreDiffViewer"]> {
  vi.resetModules();
  return (await import("../PierreDiffViewer")).PierreDiffViewer;
}

beforeEach(() => {
  viewer.renders = [];
  viewer.mounts = 0;
  theme.name = "light";
  diffs.disposeHighlighter.mockClear();
  diffs.canUseWASM.mockReturnValue(true);
  diffs.preloadHighlighter.mockReset().mockResolvedValue(undefined);
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const props = {
  filename: "flow.py",
  oldContent: "a = 1\n",
  newContent: "a = 2\n",
};

describe("PierreDiffViewer", () => {
  it("prefers Highlights and starts it before the viewer asks for a highlighter", async () => {
    const PierreDiffViewer = await freshViewer();
    const { getByTestId } = render(<PierreDiffViewer {...props} />);
    await waitFor(() => expect(getByTestId("diff")).toHaveTextContent("highlights"));
    expect(diffs.preloadHighlighter).toHaveBeenCalledTimes(1);
    expect(diffs.preloadHighlighter).toHaveBeenCalledWith({
      themes: ["pierre-dark", "pierre-light"],
      langs: [],
      preferredHighlighter: "highlights",
    });
    expect(viewer.renders[0].options).toMatchObject({
      diffStyle: "unified",
      themeType: "light",
      preferredHighlighter: "highlights",
    });
  });

  it("uses Shiki where WebAssembly SIMD is unavailable", async () => {
    diffs.canUseWASM.mockReturnValue(false);
    const PierreDiffViewer = await freshViewer();
    const { getByTestId } = render(<PierreDiffViewer {...props} />);
    expect(getByTestId("diff")).toHaveTextContent("shiki-js");
    expect(diffs.preloadHighlighter).not.toHaveBeenCalled();
  });

  it("switches every viewer to Shiki when Highlights fails to load", async () => {
    let fail: (error: Error) => void = () => {};
    diffs.preloadHighlighter.mockReturnValue(
      new Promise<void>((_, reject) => {
        fail = reject;
      }),
    );
    const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
    const PierreDiffViewer = await freshViewer();
    const { getAllByTestId } = render(
      <>
        <PierreDiffViewer {...props} />
        <PierreDiffViewer {...props} layout="split" />
      </>,
    );
    expect(viewer.mounts).toBe(0);

    await act(async () => fail(new WebAssembly.CompileError("blocked by CSP")));
    expect(getAllByTestId("diff").map((node) => node.textContent)).toEqual([
      "shiki-js",
      "shiki-js",
    ]);
    // Fresh viewers, so they request the fallback highlighter.
    expect(viewer.mounts).toBe(2);
    expect(diffs.disposeHighlighter).toHaveBeenCalledTimes(1);
    expect(warn).toHaveBeenCalledWith(
      "Highlights is unavailable for diffs; using Shiki.",
      expect.anything(),
    );
    expect(diffs.preloadHighlighter).toHaveBeenCalledTimes(1);
  });

  it("keeps file and option objects stable across unrelated renders", async () => {
    const PierreDiffViewer = await freshViewer();
    const { rerender } = render(<PierreDiffViewer {...props} />);
    await waitFor(() => expect(viewer.mounts).toBe(1));
    viewer.renders = [];
    rerender(<PierreDiffViewer {...props} />);
    rerender(<PierreDiffViewer {...props} />);
    const [first, second] = viewer.renders;
    expect(second.oldFile).toBe(first.oldFile);
    expect(second.newFile).toBe(first.newFile);
    expect(second.options).toBe(first.options);

    theme.name = "dark";
    rerender(<PierreDiffViewer {...props} newContent="a = 3\n" />);
    const third = viewer.renders[2];
    expect(third.oldFile).toBe(first.oldFile);
    expect(third.newFile).not.toBe(first.newFile);
    expect(third.options).toMatchObject({
      themeType: "dark",
      preferredHighlighter: "highlights",
    });
  });
});
