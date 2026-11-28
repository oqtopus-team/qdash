import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LiveAssistantMessage } from "../ChatMessages";

vi.mock("@/client/execution/execution", () => ({
  useGetExecution: () => ({ data: undefined }),
}));

afterEach(cleanup);

describe("LiveAssistantMessage", () => {
  it("shows the waiting status with its timer and no bot logo", () => {
    render(
      <LiveAssistantMessage
        turn={{ steps: [], startedAt: Date.now() - 3000 }}
        statusMessage="Compacting context"
      />,
    );
    const footer = screen.getByTestId("turn-activity");
    expect(screen.getByRole("status").textContent).toBe("Compacting context");
    expect(footer.textContent).toMatch(/Compacting context\d+s/);
    expect(screen.queryByRole("img", { name: "OQTOPUS" })).toBeNull();
  });
});
