import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CopilotInstructionsSettings } from "../CopilotInstructionsSettings";

const { mutate, prefs } = vi.hoisted(() => ({
  mutate: vi.fn(),
  prefs: { instructions: "", max_instructions_chars: 20 },
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ setQueryData: vi.fn(), invalidateQueries: vi.fn() }),
}));
vi.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn() }),
}));
vi.mock("@/client/copilot/copilot", () => ({
  getGetCopilotPreferencesQueryKey: () => ["prefs"],
  getGetCopilotSystemPromptQueryKey: () => ["system-prompt"],
  useGetCopilotPreferences: () => ({ data: { data: prefs }, isLoading: false }),
  useUpdateCopilotPreferences: () => ({ mutate, isPending: false }),
}));

beforeEach(() => {
  prefs.instructions = "";
});
afterEach(() => {
  cleanup();
  mutate.mockReset();
});

describe("CopilotInstructionsSettings", () => {
  it("saves edited instructions and only when they changed", () => {
    render(<CopilotInstructionsSettings />);
    const save = screen.getByRole("button", { name: "Save" }) as HTMLButtonElement;
    expect(save.disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Your instructions"), {
      target: { value: "Japanese please" },
    });
    expect(save.disabled).toBe(false);
    fireEvent.click(save);
    expect(mutate).toHaveBeenCalledWith({ data: { instructions: "Japanese please" } });
  });

  it("blocks text over the limit and offers Clear when some are saved", () => {
    prefs.instructions = "Tables";
    render(<CopilotInstructionsSettings />);
    fireEvent.change(screen.getByLabelText("Your instructions"), {
      target: { value: "x".repeat(21) },
    });
    expect((screen.getByRole("button", { name: "Save" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("21 / 20")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(mutate).toHaveBeenCalledWith({ data: { instructions: "" } });
  });
});
