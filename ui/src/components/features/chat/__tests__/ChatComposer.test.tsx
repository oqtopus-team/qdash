import {
  act,
  cleanup,
  createEvent,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { useState, type ComponentProps } from "react";
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

  it("shows Low for remembered Off on Opus and never offers disabling thinking", async () => {
    const model = { provider: "anthropic", name: "claude-opus-5-5" };
    render(
      <ChatComposer
        {...props()}
        modelOptions={[{ key: "opus", label: "Opus", model }]}
        selectedModelKey="opus"
        thinkingChoice="off"
        onThinkingChange={vi.fn()}
      />,
    );
    const trigger = screen.getByRole("button", { name: "Thinking level" });
    expect(trigger).toHaveTextContent("Thinking: Low");
    fireEvent.pointerDown(trigger);
    expect(await screen.findByRole("menuitem", { name: /Low.*always thinks/ })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /^Off/ })).toBeNull();
  });

  it("is absent where the surface does not offer it", () => {
    render(<ChatComposer {...props()} />);
    expect(screen.queryByRole("button", { name: "Thinking level" })).toBeNull();
  });
});

describe("ChatComposer model control", () => {
  const qwen = { provider: "openai-compatible-chat", name: "qwen" };
  const kimi = { provider: "openai-compatible-chat", name: "kimi" };
  const defaultOption = {
    key: "default",
    label: "qwen",
    model: null,
    isConfiguredDefault: true,
    resolvedModel: qwen,
  };
  const kimiOption = { key: "model:openai-compatible-chat:kimi", label: "kimi", model: kimi };

  it("names the model the default resolves to and switches between configured models", async () => {
    const onModelChange = vi.fn();
    render(
      <ChatComposer
        {...props()}
        modelOptions={[defaultOption, kimiOption]}
        selectedModelKey="default"
        onModelChange={onModelChange}
      />,
    );
    const trigger = screen.getByRole("button", { name: "Chat model: qwen" });
    expect(trigger).toHaveTextContent("qwendefault");

    fireEvent.pointerDown(trigger);
    fireEvent.click(await screen.findByRole("menuitem", { name: /kimi/ }));
    expect(onModelChange).toHaveBeenCalledWith("model:openai-compatible-chat:kimi");
  });

  it("shows a single configured model and why it cannot be switched", () => {
    render(<ChatComposer {...props()} modelOptions={[defaultOption]} selectedModelKey="default" />);
    const model = screen.getByRole("button", {
      name: "Chat model: qwen. Only one chat model is configured",
    });
    expect(model).toHaveAttribute("aria-disabled", "true");
    fireEvent.pointerDown(model);
    expect(screen.queryByRole("menu")).toBeNull();
  });

  it("waits for the model list before offering a switch", () => {
    render(
      <ChatComposer
        {...props()}
        modelOptions={[{ ...defaultOption, label: "Configured default", resolvedModel: null }]}
        selectedModelKey="default"
        modelStatus="loading"
      />,
    );
    expect(screen.getByRole("button", { name: /Chat model: Loading models/ })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
  });

  it("says no model can answer when none has its API key set", () => {
    const none = { ...defaultOption, label: "No chat model available", resolvedModel: null };
    render(
      <ChatComposer
        {...props()}
        disabled
        modelOptions={[none]}
        selectedModelKey="default"
        modelStatus="none"
      />,
    );
    expect(
      screen.getByRole("button", {
        name: "Chat model: No chat model available. No chat model has its API key set",
      }),
    ).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("button", { name: /send/i })).toBeDisabled();
  });

  it("cannot be switched while an answer streams", () => {
    render(
      <ChatComposer
        {...props()}
        isStreaming
        modelOptions={[defaultOption, kimiOption]}
        selectedModelKey={kimiOption.key}
      />,
    );
    expect(screen.getByRole("button", { name: "Chat model: kimi" })).toBeDisabled();
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
      "/settings?tab=agent",
    );
  });
});

describe("ChatComposer narrow layout", () => {
  // jsdom has no layout, so these pin the flex contract that keeps a phone-width
  // composer inside its frame: the selectors shrink and truncate, the send controls do not.
  const option = {
    key: "default",
    label: "a-very-long-configured-model-name",
    model: null,
    isConfiguredDefault: true,
    resolvedModel: null,
  };
  const other = { key: "other", label: "other", model: null };

  it("keeps the selectors in a shrinkable group apart from the send button", () => {
    render(
      <ChatComposer
        {...props()}
        modelOptions={[option, other]}
        selectedModelKey="default"
        thinkingChoice="auto"
        thinkingModelDefault="medium"
        onThinkingChange={vi.fn()}
        instructionsActive
      />,
    );
    const group = screen.getByRole("group", { name: "Message options" });
    expect(group).toHaveClass("min-w-0", "flex-1");

    for (const name of [/Chat model/, "Thinking level"]) {
      const trigger = screen.getByRole("button", { name });
      expect(group).toContainElement(trigger);
      expect(trigger).toHaveClass("min-w-0", "shrink");
    }
    expect(group).toContainElement(screen.getByRole("link", { name: "Your instructions apply" }));

    const send = screen.getByRole("button", { name: "Send message" });
    expect(group).not.toContainElement(send);
    expect(send.parentElement).toHaveClass("shrink-0");
  });

  it("shows the short thinking label until the composer is wide enough for the full one", () => {
    render(
      <ChatComposer
        {...props()}
        thinkingChoice="auto"
        thinkingModelDefault="medium"
        onThinkingChange={vi.fn()}
      />,
    );
    const trigger = screen.getByRole("button", { name: "Thinking level" });
    expect(within(trigger).getByText("Auto · medium")).toHaveClass("truncate", "@md:hidden");
    expect(within(trigger).getByText("Thinking: Auto (medium)")).toHaveClass(
      "hidden",
      "@md:inline",
    );
  });

  it("uses a 16px input on phones so focusing it does not zoom the page", () => {
    render(<ChatComposer {...props()} />);
    expect(screen.getByRole("textbox")).toHaveClass("text-base", "sm:text-sm");
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

describe("ChatComposer skill menu", () => {
  const skills = [
    { name: "qdash-characterization", description: "Remeasure T1 and T2." },
    { name: "qdash-one-qubit-calibration", description: "Calibrate single qubits." },
    { name: "qcaleval", description: "Evaluate calibration plots." },
  ];

  /** A composer that owns its text, as ChatThread does. */
  function Controlled(overrides: Partial<ComponentProps<typeof ChatComposer>>) {
    const [value, setValue] = useState("");
    return (
      <ChatComposer {...props()} value={value} onChange={setValue} skills={skills} {...overrides} />
    );
  }

  const setup = (overrides: Partial<ComponentProps<typeof ChatComposer>> = {}) => {
    const onSubmit = vi.fn();
    render(<Controlled onSubmit={onSubmit} {...overrides} />);
    const box = screen.getByRole("combobox", { name: "Message" });
    act(() => box.focus());
    return { box, onSubmit };
  };
  const type = (box: HTMLElement, value: string) => fireEvent.change(box, { target: { value } });

  it("offers the skills with their descriptions after a leading slash", () => {
    const { box } = setup();
    expect(screen.queryByRole("listbox")).toBeNull();
    type(box, "/");
    const list = screen.getByRole("listbox", { name: "Skills" });
    expect(within(list).getAllByRole("option")).toHaveLength(3);
    expect(list).toHaveTextContent("/skill:qdash-characterization");
    expect(list).toHaveTextContent("Remeasure T1 and T2.");
    expect(box).toHaveAttribute("aria-expanded", "true");
    expect(box).toHaveAttribute("aria-activedescendant", screen.getAllByRole("option")[0].id);
  });

  it("filters as the name is typed and closes once arguments start", () => {
    const { box } = setup();
    type(box, "/cal");
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
      expect.stringContaining("qdash-one-qubit-calibration"),
      expect.stringContaining("qcaleval"),
    ]);
    type(box, "/skill:qdash-ch");
    expect(screen.getAllByRole("option")).toHaveLength(1);
    type(box, "/skill:qdash-characterization Q0");
    expect(screen.queryByRole("listbox")).toBeNull();
    type(box, "/nothing-matches");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("moves with the arrow keys and inserts the active skill on Enter without sending", () => {
    const { box, onSubmit } = setup();
    type(box, "/");
    fireEvent.keyDown(box, { key: "ArrowDown" });
    fireEvent.keyDown(box, { key: "ArrowDown" });
    expect(screen.getAllByRole("option")[2]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(box, { key: "ArrowDown" });
    expect(screen.getAllByRole("option")[0]).toHaveAttribute("aria-selected", "true");
    fireEvent.keyDown(box, { key: "ArrowUp" });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(box).toHaveValue("/skill:qcaleval ");
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("inserts the active skill on Tab", () => {
    const { box } = setup();
    type(box, "/qd");
    fireEvent.keyDown(box, { key: "Tab" });
    expect(box).toHaveValue("/skill:qdash-characterization ");
  });

  it("inserts a skill picked with the mouse and keeps focus in the field", () => {
    const { box, onSubmit } = setup();
    type(box, "/");
    const option = screen.getByRole("option", { name: /qdash-one-qubit-calibration/ });
    const down = createEvent.mouseDown(option.firstElementChild!);
    fireEvent(option.firstElementChild!, down);
    expect(down.defaultPrevented).toBe(true);
    expect(box).toHaveValue("/skill:qdash-one-qubit-calibration ");
    expect(box).toHaveFocus();
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("dismisses on Escape until the text changes, then Enter sends as usual", () => {
    const { box, onSubmit } = setup();
    type(box, "/qd");
    const escape = createEvent.keyDown(box, { key: "Escape" });
    fireEvent(box, escape);
    expect(escape.defaultPrevented).toBe(true);
    expect(screen.queryByRole("listbox")).toBeNull();
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onSubmit).toHaveBeenCalledTimes(1);
    type(box, "/qda");
    expect(screen.getByRole("listbox")).toBeInTheDocument();
  });

  it("leaves Enter to the IME while composing", () => {
    const { box, onSubmit } = setup();
    type(box, "/");
    fireEvent.keyDown(box, { key: "Enter", isComposing: true });
    expect(box).toHaveValue("/");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("keeps Shift+Enter and plain Enter for ordinary messages", () => {
    const { box, onSubmit } = setup();
    type(box, "calibrate Q0");
    expect(screen.queryByRole("listbox")).toBeNull();
    const shiftEnter = createEvent.keyDown(box, { key: "Enter", shiftKey: true });
    fireEvent(box, shiftEnter);
    expect(shiftEnter.defaultPrevented).toBe(false);
    fireEvent.keyDown(box, { key: "Enter" });
    expect(onSubmit).toHaveBeenCalledTimes(1);
  });

  it("stays closed while the field is unfocused, an answer streams, or the composer is disabled", () => {
    const first = setup();
    act(() => first.box.blur());
    type(first.box, "/");
    expect(screen.queryByRole("listbox")).toBeNull();
    cleanup();

    const streaming = setup({ isStreaming: true, steerable: true });
    type(streaming.box, "/");
    expect(screen.queryByRole("listbox")).toBeNull();
    cleanup();

    render(<Controlled disabled />);
    expect(screen.getByRole("combobox")).toBeDisabled();
  });

  it("is a plain text field when no skills are loaded", () => {
    render(<Controlled skills={[]} />);
    const box = screen.getByRole("textbox", { name: "Message" });
    act(() => box.focus());
    type(box, "/");
    expect(screen.queryByRole("listbox")).toBeNull();
  });
});
