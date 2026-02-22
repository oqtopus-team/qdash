import { describe, it, expect } from "vitest";

import { URL_DEFAULTS } from "../types";
import type { TimeRange, SelectionMode, MetricType, ProvenanceTab } from "../types";

describe("URL_DEFAULTS", () => {
  it("has expected default values", () => {
    expect(URL_DEFAULTS.DATE).toBe("latest");
    expect(URL_DEFAULTS.TASK).toBe("CheckRabi");
    expect(URL_DEFAULTS.VIEW).toBe("1q");
    expect(URL_DEFAULTS.SHOW_ERROR_RATE).toBe(false);
  });

  it("has expected CDF_PARAMETERS array", () => {
    expect(URL_DEFAULTS.CDF_PARAMETERS).toEqual(["t1", "t2_echo", "t2_star"]);
  });

  it("URL_DEFAULTS is readonly", () => {
    // TypeScript enforces this at compile time via `as const`,
    // but we can verify the runtime values are stable
    const copy = { ...URL_DEFAULTS };
    expect(copy).toEqual({
      DATE: "latest",
      TASK: "CheckRabi",
      VIEW: "1q",
      CDF_PARAMETERS: ["t1", "t2_echo", "t2_star"],
      SHOW_ERROR_RATE: false,
    });
  });
});

describe("type exports", () => {
  it("TimeRange accepts valid values", () => {
    const values: TimeRange[] = ["1d", "7d", "30d", "custom"];
    expect(values).toHaveLength(4);
  });

  it("SelectionMode accepts valid values", () => {
    const values: SelectionMode[] = ["latest", "best", "average"];
    expect(values).toHaveLength(3);
  });

  it("MetricType accepts valid values", () => {
    const values: MetricType[] = ["qubit", "coupling"];
    expect(values).toHaveLength(2);
  });

  it("ProvenanceTab accepts valid values", () => {
    const values: ProvenanceTab[] = ["history", "lineage", "compare", "seeds"];
    expect(values).toHaveLength(4);
  });
});
