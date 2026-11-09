import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TooltipProvider } from "@/components/ui/Tooltip";

import { ChatPlotlyChart } from "../ChatPlotlyChart";
import { ChatUiBlock } from "../ChatUiBlock";

// Exercise the real Plot wrapper, including rejected asynchronous renders.
vi.mock("next/dynamic", async () => {
  const { default: Plot } = await import("@/components/charts/Plot");
  return { default: () => Plot };
});
vi.mock("plotly.js-dist-min", () => ({
  default: {
    react: vi.fn().mockRejectedValue(new Error("plotly failed")),
    purge: vi.fn(),
    Plots: { resize: vi.fn() },
  },
}));
vi.mock("@/contexts/ThemeContext", () => ({ useIsDarkTheme: () => false }));

beforeEach(() => {
  vi.spyOn(console, "error").mockImplementation(() => {});
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("chart rendering failures", () => {
  it("replaces a UI block with its fallback when its chart fails", async () => {
    render(
      <TooltipProvider>
        <ChatUiBlock
          ui={{
            version: 1,
            spec: {
              root: "c",
              elements: {
                c: { type: "Chart", props: { data: [{ y: [1, 2] }], layout: { title: "T1" } } },
              },
            },
            fallback: "[Chart: T1]",
          }}
        />
      </TooltipProvider>,
    );
    expect(await screen.findByText("This view could not be displayed.")).toBeInTheDocument();
    expect(screen.getByText("[Chart: T1]")).toBeInTheDocument();
    expect(screen.queryByText(/Chart rendering failed/)).not.toBeInTheDocument();
  });

  it("keeps the inline message for a standalone chart", async () => {
    render(
      <TooltipProvider>
        <ChatPlotlyChart data={[{ y: [1] }]} layout={{}} />
      </TooltipProvider>,
    );
    expect(await screen.findByText(/Chart rendering failed/)).toBeInTheDocument();
  });
});
