import { describe, expect, it } from "vitest";

import { sessionStatusLabel } from "@/components/features/agent-session/interventionLabels";

import { sessionStatusBadgeClass } from "../agentSessionDisplay";
import { getStatusBadgeClass } from "../ExecutionListCard";

describe("sessionStatusBadgeClass", () => {
  it("gives analogous session states the Execution status colors", () => {
    expect(sessionStatusBadgeClass("active")).toBe(getStatusBadgeClass("running"));
    expect(sessionStatusBadgeClass("completed")).toBe(getStatusBadgeClass("completed"));
    expect(sessionStatusBadgeClass("cancelled")).toBe(getStatusBadgeClass("cancelled"));
  });

  it("keeps waiting for a person distinct, and never uses the failed color", () => {
    expect(sessionStatusBadgeClass("waiting_for_human")).toBe("badge-warning");
    expect(sessionStatusBadgeClass("active")).not.toBe("badge-warning");
    for (const status of [
      "active",
      "waiting_for_human",
      "completed",
      "cancelled",
      "expired",
      "new",
    ]) {
      expect(sessionStatusBadgeClass(status)).not.toBe(getStatusBadgeClass("failed"));
    }
    expect(sessionStatusBadgeClass("expired")).toBe("badge-ghost");
  });

  it("always pairs the color with a text label", () => {
    expect(sessionStatusLabel("waiting_for_human")).toBe("Paused for an expert");
    expect(sessionStatusLabel("expired")).toBe("Expired");
  });
});
