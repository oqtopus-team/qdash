import { act, cleanup, createEvent, fireEvent, render, screen } from "@testing-library/react";
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

describe("ChatComposer thinking menu", () => {
  it("shows what Auto resolves to and reports the chosen level", async () => {
    const onThinkingChange = vi.fn();
    render(
      <ChatComposer
        {...props()}
        thinkingChoice="auto"
        thinkingModelDefault="high"
        onThinkingChange={onThinkingChange}
      />,
    );
    const trigger = screen.getByRole("button", { name: "Thinking level" });
    expect(trigger.textContent).toContain("Thinking: Auto (high)");

    fireEvent.pointerDown(trigger);
    fireEvent.click(await screen.findByRole("menuitem", { name: /Off/ }));
    expect(onThinkingChange).toHaveBeenCalledWith("off");
  });

  it("is absent where the surface does not offer it", () => {
    render(<ChatComposer {...props()} />);
    expect(screen.queryByRole("button", { name: "Thinking level" })).toBeNull();
  });
});

describe("thinkingLabel", () => {
  it("names the level, and Auto with its default when known", async () => {
    const { thinkingLabel } = await import("../ChatComposer");
    expect(thinkingLabel("medium", "high")).toBe("Thinking: Medium");
    expect(thinkingLabel("auto", null)).toBe("Thinking: Auto");
    expect(thinkingLabel("auto", "low", true)).toBe("Auto · low");
  });
});

describe("ChatComposer instructions indicator", () => {
  it("links to the user's instructions only when they apply", () => {
    const { rerender } = render(<ChatComposer {...props()} />);
    expect(screen.queryByRole("link", { name: "Your instructions apply" })).toBeNull();
    rerender(<ChatComposer {...props()} instructionsActive />);
    expect(screen.getByRole("link", { name: "Your instructions apply" }).getAttribute("href")).toBe(
      "/settings?tab=copilot",
    );
  });
});

describe("ChatComposer height", () => {
  const LINE = 24;
  let width = 0;
  let observed: ResizeObserverCallback | null = null;

  /** jsdom has no layout: wrap the textarea's text at `width` characters per line. */
  const fakeLayout = () => {
    vi.spyOn(HTMLTextAreaElement.prototype, "clientWidth", "get").mockImplementation(() => width);
    vi.spyOn(HTMLTextAreaElement.prototype, "scrollHeight", "get").mockImplementation(function (
      this: HTMLTextAreaElement,
    ) {
      const text = this.value || this.placeholder;
      const lines = text
        .split("\n")
        .reduce((n, line) => n + Math.max(1, Math.ceil(line.length / Math.max(width, 1))), 0);
      return lines * LINE;
    });
    vi.stubGlobal(
      "ResizeObserver",
      class {
        constructor(callback: ResizeObserverCallback) {
          observed = callback;
        }
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    );
  };

  const resizeTo = (next: number) => {
    width = next;
    act(() => observed?.([], {} as ResizeObserver));
  };

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    observed = null;
  });

  it("drops to one line once a sidebar opening from zero width settles", () => {
    width = 0;
    fakeLayout();
    render(<ChatComposer {...props()} value="" />);
    const textarea = screen.getByRole("textbox");
    // Mounted mid-animation: the placeholder wraps per character up to the cap.
    expect(textarea.style.height).toBe("240px");

    resizeTo(360);
    expect(textarea.style.height).toBe(`${LINE}px`);
  });

  it("grows with multiline input up to the cap and shrinks back when cleared", () => {
    width = 360;
    fakeLayout();
    const { rerender } = render(<ChatComposer {...props()} value="" />);
    const textarea = screen.getByRole("textbox");
    expect(textarea.style.height).toBe(`${LINE}px`);

    rerender(<ChatComposer {...props()} value={"a\nb\nc"} />);
    expect(textarea.style.height).toBe(`${3 * LINE}px`);

    rerender(<ChatComposer {...props()} value={Array(30).fill("x").join("\n")} />);
    expect(textarea.style.height).toBe("240px");

    rerender(<ChatComposer {...props()} value="" />);
    expect(textarea.style.height).toBe(`${LINE}px`);
  });

  it("re-wraps the current text when the sidebar is narrowed", () => {
    width = 100;
    fakeLayout();
    render(<ChatComposer {...props()} value={"word ".repeat(30)} />);
    const textarea = screen.getByRole("textbox");
    expect(textarea.style.height).toBe(`${2 * LINE}px`);

    resizeTo(50);
    expect(textarea.style.height).toBe(`${3 * LINE}px`);
  });
});
