import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AgentSystemPromptView } from "../AgentSystemPromptView";

const { query } = vi.hoisted(() => ({ query: vi.fn() }));

vi.mock("@/client/agent/agent", () => ({
  useGetAgentSystemPrompt: (options: { query: { enabled: boolean } }) => query(options),
}));

afterEach(() => {
  cleanup();
  query.mockReset();
});

describe("AgentSystemPromptView", () => {
  it("loads only when opened and shows the prompt, the user's part and the tools", () => {
    query.mockImplementation(({ query: { enabled } }) =>
      enabled
        ? {
            data: {
              data: {
                system_prompt: "You are QDash Agent.",
                user_preferences: "<user-preferences>\nUse tables.\n</user-preferences>",
                tools: ["ask_user", "run_python"],
              },
            },
            isLoading: false,
            error: null,
          }
        : { data: undefined, isLoading: false, error: null },
    );
    render(<AgentSystemPromptView />);
    expect(query).toHaveBeenLastCalledWith({ query: { enabled: false, staleTime: 30_000 } });

    const details = screen.getByText("What Agent is told").closest("details") as HTMLDetailsElement;
    details.open = true;
    fireEvent(details, new Event("toggle"));

    expect(screen.getByText("You are QDash Agent.")).toBeTruthy();
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
    render(<AgentSystemPromptView />);
    expect(screen.getByText("None: you have not set any.")).toBeTruthy();
  });
});
