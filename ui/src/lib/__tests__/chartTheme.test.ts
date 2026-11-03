import type { Layout } from "plotly.js";
import { describe, expect, it } from "vitest";

import { chartTheme, seriesColor, themedLayout } from "@/lib/chartTheme";

describe("themedLayout", () => {
  const light = chartTheme(false);
  const dark = chartTheme(true);

  it("fills transparent backgrounds, themed axes and the colorway", () => {
    const layout = themedLayout({ xaxis: { title: { text: "Time" } } }, dark);
    expect(layout.paper_bgcolor).toBe("transparent");
    expect(layout.plot_bgcolor).toBe("transparent");
    expect(layout.colorway).toEqual([...dark.series]);
    expect(layout.font?.color).toBe(dark.text);
    expect(layout.xaxis?.gridcolor).toBe(dark.grid);
    expect(layout.xaxis?.title).toEqual({ text: "Time", font: { color: dark.muted } });
    expect(layout.yaxis?.tickfont).toEqual({ color: dark.muted });
  });

  it("lets caller values win", () => {
    const layout = themedLayout(
      {
        font: { color: "#123456" },
        xaxis: { gridcolor: "red", title: { text: "Time", font: { color: "blue" } } },
      },
      light,
    );
    expect(layout.font).toEqual(expect.objectContaining({ color: "#123456" }));
    expect(layout.xaxis?.gridcolor).toBe("red");
    expect(layout.xaxis?.title).toEqual({ text: "Time", font: { color: "blue" } });
  });

  it("accepts a null axis title from a fetched figure", () => {
    const fetched = { yaxis: { title: null } } as unknown as Partial<Layout>;
    expect(() => themedLayout(fetched, light)).not.toThrow();
    expect(themedLayout(fetched, light).yaxis?.title).toBeNull();
  });

  it("leaves a figure that paints its own paper alone", () => {
    const layout = themedLayout(
      { paper_bgcolor: "white", xaxis: { title: { text: "x" } }, legend: { bgcolor: "white" } },
      dark,
    );
    expect(layout.paper_bgcolor).toBe("white");
    expect(layout.colorway).toBeUndefined();
    expect(layout.plot_bgcolor).toBeUndefined();
    expect(layout.font?.color).toBeUndefined();
    expect(layout.font?.family).toBeTruthy();
    expect(layout.xaxis?.gridcolor).toBeUndefined();
    expect(layout.xaxis?.title).toEqual({ text: "x" });
    expect(layout.legend).toEqual({ bgcolor: "white" });
  });

  it("treats a zero-alpha paper color as transparent", () => {
    const layout = themedLayout({ paper_bgcolor: "rgba(0, 0, 0, 0)" }, dark);
    expect(layout.paper_bgcolor).toBe("rgba(0, 0, 0, 0)");
    expect(layout.font?.color).toBe(dark.text);
    expect(layout.colorway).toEqual([...dark.series]);
  });
});

describe("seriesColor", () => {
  it("wraps around the palette", () => {
    const theme = chartTheme(false);
    expect(seriesColor(theme, 0)).toBe(theme.series[0]);
    expect(seriesColor(theme, theme.series.length + 2)).toBe(theme.series[2]);
  });
});
