import { cleanup, createEvent, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ChatComposer } from "../ChatComposer";

afterEach(cleanup);

const props = () => ({
  value: "Evaluate",
  onChange: vi.fn(),
  onSubmit: vi.fn(),
  onStop: vi.fn(),
  isStreaming: false,
  modelOptions: [],
  selectedModelKey: "",
  onModelChange: vi.fn(),
  onAttach: vi.fn(),
});

describe("ChatComposer attachments", () => {
  it.each([false, true])("cancels file navigation, including while streaming=%s", (isStreaming) => {
    const handlers = props();
    render(<ChatComposer {...handlers} isStreaming={isStreaming} />);
    const form = screen.getByRole("textbox").closest("form")!;
    const file = new File(["gif"], "a.gif", { type: "image/gif" });
    for (const name of ["dragOver", "drop"] as const) {
      const event = createEvent[name](form, { dataTransfer: { files: [file] } });
      fireEvent(form, event);
      expect(event.defaultPrevented).toBe(true);
    }
    expect(handlers.onAttach).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("disables button and Enter submission during image preparation", () => {
    const handlers = props();
    render(<ChatComposer {...handlers} isStaging />);
    expect(screen.getByRole("button", { name: "Send message" })).toBeDisabled();
    fireEvent.keyDown(screen.getByRole("textbox"), { key: "Enter" });
    expect(handlers.onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent("Preparing images");
  });
});
