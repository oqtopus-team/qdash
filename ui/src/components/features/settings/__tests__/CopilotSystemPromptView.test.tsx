import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CopilotSystemPromptView } from "../CopilotSystemPromptView";

const { query } = vi.hoisted(() => ({ query: vi.fn() }));

vi.mock("@/client/copilot/copilot", () => ({
  useGetCopilotSystemPrompt: (options: { query: { enabled: boolean } }) => query(options),
}));

afterEach(() => {
  cleanup();
  query.mockReset();
});

describe("CopilotSystemPromptView", () => {
  it("loads only when opened and shows the prompt, the user's part and the tools", () => {
    query.mockImplementation(({ query: { enabled } }) =>
      enabled
        ? {
            data: {
              data: {
                system_prompt: "You are QDash Copilot.",
                user_preferences: "<user-preferences>\nUse tables.\n</user-preferences>",
                tools: ["ask_user", "run_python"],
              },
            },
            isLoading: false,
            error: null,
          }
        : { data: undefined, isLoading: false, error: null },
    );
    render(<CopilotSystemPromptView />);
    expect(query).toHaveBeenLastCalledWith({ query: { enabled: false, staleTime: 30_000 } });

    const details = screen
      .getByText("What Copilot is told")
      .closest("details") as HTMLDetailsElement;
    details.open = true;
    fireEvent(details, new Event("toggle"));

    expect(screen.getByText("You are QDash Copilot.")).toBeTruthy();
    expect(screen.getByText(/Use tables\./)).toBeTruthy();
    expect(screen.getByText("run_python")).toBeTruthy();
    expect(screen.getByText("Tools offered (2)")).toBeTruthy();
  });

  it("says when the user has no instructions", () => {
    query.mockReturnValue({
      data: { data: { system_prompt: "p", user_preferences: null, tools: [] } },
      isLoading: false,
      error: null,
    });
    render(<CopilotSystemPromptView />);
    expect(screen.getByText("None: you have not set any.")).toBeTruthy();
  });
});
