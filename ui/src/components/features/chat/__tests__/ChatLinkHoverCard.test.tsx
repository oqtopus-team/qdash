import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  CARD_CLOSE_DELAY_MS,
  CARD_OPEN_DELAY_MS,
} from "@/components/features/link-preview/LinkHoverCardProvider";
import { ChatLinkPreviewProvider } from "../ChatLinkPreview";
import { ChatLink, ChatMarkdown } from "../ChatMarkdown";

const useGetTaskResult = vi.fn();
const useGetExecution = vi.fn();
const useGetForumPost = vi.fn();
vi.mock("@/client/task/task", () => ({
  useGetTaskResult: (...args: unknown[]) => useGetTaskResult(...args),
}));
vi.mock("@/client/execution/execution", () => ({
  useGetExecution: (...args: unknown[]) => useGetExecution(...args),
}));
vi.mock("@/client/forum/forum", () => ({
  useGetForumPost: (...args: unknown[]) => useGetForumPost(...args),
}));

const TASK_RESULT = {
  task_id: "t1",
  task_name: "CheckRabi",
  qid: "0",
  chip_id: "64Qv3",
  status: "completed",
  execution_id: "20261006-012",
  figure_path: ["exec/1/CheckRabi_0.png"],
  json_figure_path: [],
  raw_data_path: [],
  input_parameters: {},
  output_parameters: { rabi_frequency: { value: 12.6649, unit: "MHz" }, shots: 1024 },
};

const MARKDOWN = [
  "See [the Rabi result](http://localhost:3000/task-results/t1),",
  "[the run](/executions/20261006-012),",
  "[the thread](/forum/posts/p1),",
  "[the figure](/api/executions/figure?path=exec%2F1%2FCheckRabi_0.png),",
  "[the chip page](/chip/64Qv3?tab=t1) and [the paper](https://arxiv.org/abs/2401.00001).",
  "The path task-results/t2 is plain text.",
].join(" ");

let fetchSpy: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  vi.useFakeTimers();
  fetchSpy = vi.spyOn(globalThis, "fetch").mockRejectedValue(new Error("no network in tests"));
  useGetTaskResult.mockReturnValue({ data: { data: TASK_RESULT } });
  useGetExecution.mockReturnValue({
    data: {
      data: {
        name: "pipeline-x",
        status: "running",
        chip_id: "64Qv3",
        start_at: "2026-10-06T01:00:00+00:00",
        note: {},
        task: [{}, {}],
      },
    },
  });
  useGetForumPost.mockReturnValue({
    data: {
      data: {
        id: "p1",
        title: "Q00 drift",
        username: "alice",
        category: "calibration",
        content: "T1 dropped after the cooldown.",
        reply_count: 2,
      },
    },
  });
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  fetchSpy.mockRestore();
  useGetTaskResult.mockReset();
  useGetExecution.mockReset();
  useGetForumPost.mockReset();
});

function wrap(ui: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <ChatLinkPreviewProvider>{ui}</ChatLinkPreviewProvider>
    </QueryClientProvider>,
  );
}

const link = (name: string) => screen.getByRole("link", { name });
const card = () => screen.queryByRole("tooltip");

function hover(element: Element) {
  fireEvent.pointerOver(element, { pointerType: "mouse" });
}

function unhover(element: Element, to: Element = document.body) {
  fireEvent.pointerOut(element, { pointerType: "mouse", relatedTarget: to });
}

function advance(ms: number) {
  act(() => {
    vi.advanceTimersByTime(ms);
  });
}

describe("chat link hover cards", () => {
  it("waits for the hover delay before showing a task result summary, and fetches only then", () => {
    wrap(<ChatMarkdown>{MARKDOWN}</ChatMarkdown>);
    // Rendering an answer fetches nothing for its links.
    expect(useGetTaskResult).not.toHaveBeenCalled();

    hover(link("the Rabi result"));
    advance(CARD_OPEN_DELAY_MS - 1);
    expect(card()).toBeNull();
    expect(useGetTaskResult).not.toHaveBeenCalled();

    advance(1);
    const shown = screen.getByRole("tooltip");
    expect(useGetTaskResult).toHaveBeenCalledWith("t1", expect.anything());
    expect(shown).toHaveTextContent("Task result");
    expect(shown).toHaveTextContent("CheckRabi");
    expect(shown).toHaveTextContent("completed");
    expect(shown).toHaveTextContent("1 figure");
    expect(shown).toHaveTextContent("12.665 MHz");
    expect(link("the Rabi result")).toHaveAttribute("aria-describedby", shown.id);
    // The hover card is a summary, not the dialog.
    expect(screen.queryByTestId("chat-link-preview")).toBeNull();
  });

  it("never opens when the pointer passes over a link before the delay", () => {
    wrap(<ChatMarkdown>{MARKDOWN}</ChatMarkdown>);
    hover(link("the run"));
    advance(CARD_OPEN_DELAY_MS / 2);
    unhover(link("the run"));
    advance(CARD_OPEN_DELAY_MS * 2);
    expect(card()).toBeNull();
    expect(useGetExecution).not.toHaveBeenCalled();
  });

  it("stays open while the pointer moves from the link into the card, then closes", () => {
    wrap(<ChatMarkdown>{MARKDOWN}</ChatMarkdown>);
    hover(link("the thread"));
    advance(CARD_OPEN_DELAY_MS);
    const shown = screen.getByRole("tooltip");
    expect(shown).toHaveTextContent("Q00 drift");
    expect(shown).toHaveTextContent("alice");
    expect(shown).toHaveTextContent("2 replies");
    expect(shown).toHaveTextContent("T1 dropped");

    unhover(link("the thread"), shown);
    fireEvent.pointerEnter(shown, { pointerType: "mouse" });
    advance(CARD_CLOSE_DELAY_MS * 4);
    expect(card()).toBe(shown);

    fireEvent.pointerLeave(shown, { pointerType: "mouse" });
    advance(CARD_CLOSE_DELAY_MS - 1);
    expect(card()).not.toBeNull();
    advance(1);
    expect(card()).toBeNull();
    expect(link("the thread")).not.toHaveAttribute("aria-describedby");
  });

  it("does not close when the pointer moves between a link's own children", () => {
    wrap(<ChatMarkdown>{"Open [the `CheckRabi` result](/task-results/t1)."}</ChatMarkdown>);
    const anchor = link("the CheckRabi result");
    const code = anchor.querySelector("code")!;
    hover(code);
    advance(CARD_OPEN_DELAY_MS);
    unhover(code, anchor);
    advance(CARD_CLOSE_DELAY_MS * 2);
    expect(card()).toHaveTextContent("CheckRabi");
  });

  it("switches straight to the next link while a card is open", () => {
    wrap(<ChatMarkdown>{MARKDOWN}</ChatMarkdown>);
    hover(link("the run"));
    advance(CARD_OPEN_DELAY_MS);
    expect(card()).toHaveTextContent("pipeline-x");

    unhover(link("the run"), link("the thread"));
    hover(link("the thread"));
    expect(card()).toHaveTextContent("Q00 drift");
  });

  it("summarizes an execution with its chip, start and task count", () => {
    wrap(<ChatMarkdown>{MARKDOWN}</ChatMarkdown>);
    hover(link("the run"));
    advance(CARD_OPEN_DELAY_MS);
    const shown = screen.getByRole("tooltip");
    expect(useGetExecution).toHaveBeenCalledWith("20261006-012", expect.anything());
    expect(shown).toHaveTextContent("Execution");
    expect(shown).toHaveTextContent("pipeline-x");
    expect(shown).toHaveTextContent("running");
    expect(shown).toHaveTextContent("64Qv3");
    expect(shown).toHaveTextContent("2 tasks");
    expect(shown).toHaveTextContent("20261006-012");
  });

  it("shows loading and error states for a record card", () => {
    useGetTaskResult.mockReturnValue({ data: undefined, isError: false });
    const { rerender } = wrap(<ChatMarkdown>{MARKDOWN}</ChatMarkdown>);
    hover(link("the Rabi result"));
    advance(CARD_OPEN_DELAY_MS);
    expect(card()).toHaveTextContent("Loading task result");

    useGetTaskResult.mockReturnValue({ data: undefined, isError: true });
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <ChatLinkPreviewProvider>
          <ChatMarkdown>{MARKDOWN}</ChatMarkdown>
        </ChatLinkPreviewProvider>
      </QueryClientProvider>,
    );
    hover(link("the Rabi result"));
    advance(CARD_OPEN_DELAY_MS);
    expect(card()).toHaveTextContent("Could not load this task result.");
  });

  it("previews a figure link as an image", () => {
    wrap(<ChatMarkdown>{MARKDOWN}</ChatMarkdown>);
    hover(link("the figure"));
    advance(CARD_OPEN_DELAY_MS);
    const shown = screen.getByRole("tooltip");
    expect(shown).toHaveTextContent("Figure");
    const image = screen.getByRole("img", { name: "CheckRabi_0" });
    expect(image).toHaveAttribute(
      "src",
      `/api/executions/figure?path=${encodeURIComponent("exec/1/CheckRabi_0.png")}`,
    );
  });

  it("names internal and external destinations without fetching them", () => {
    wrap(<ChatMarkdown>{MARKDOWN}</ChatMarkdown>);
    hover(link("the chip page"));
    advance(CARD_OPEN_DELAY_MS);
    expect(card()).toHaveTextContent("QDash page");
    expect(card()).toHaveTextContent("/chip/64Qv3?tab=t1");

    unhover(link("the chip page"), link("the paper"));
    hover(link("the paper"));
    expect(card()).toHaveTextContent("External link");
    expect(card()).toHaveTextContent("arxiv.org");
    expect(card()).toHaveTextContent("https://arxiv.org/abs/2401.00001");

    expect(fetchSpy).not.toHaveBeenCalled();
    expect(useGetTaskResult).not.toHaveBeenCalled();
    expect(useGetExecution).not.toHaveBeenCalled();
    expect(useGetForumPost).not.toHaveBeenCalled();
  });

  it("does not treat plain-text paths as links", () => {
    const { container } = wrap(<ChatMarkdown>{MARKDOWN}</ChatMarkdown>);
    expect(screen.getAllByRole("link")).toHaveLength(6);
    expect(container).toHaveTextContent("The path task-results/t2 is plain text.");
  });

  it("opens at once on keyboard focus, and closes on Escape or blur", () => {
    wrap(<ChatMarkdown>{MARKDOWN}</ChatMarkdown>);
    act(() => link("the run").focus());
    expect(card()).toHaveTextContent("pipeline-x");
    // Focus stays on the link.
    expect(document.activeElement).toBe(link("the run"));

    fireEvent.keyDown(link("the run"), { key: "Escape" });
    expect(card()).toBeNull();
    expect(document.activeElement).toBe(link("the run"));

    act(() => link("the thread").focus());
    expect(card()).toHaveTextContent("Q00 drift");
    act(() => link("the thread").blur());
    advance(CARD_CLOSE_DELAY_MS);
    expect(card()).toBeNull();
  });

  it("keeps a focused card open on blur while the pointer is inside it", () => {
    wrap(<ChatMarkdown>{MARKDOWN}</ChatMarkdown>);
    act(() => link("the thread").focus());
    const shown = screen.getByRole("tooltip");
    fireEvent.pointerEnter(shown, { pointerType: "mouse" });
    act(() => link("the thread").blur());
    advance(CARD_CLOSE_DELAY_MS * 4);
    expect(card()).toBe(shown);
  });

  it("keeps the card open while either focus or pointer remains on the link", () => {
    wrap(<ChatMarkdown>{MARKDOWN}</ChatMarkdown>);
    const anchor = link("the thread");
    act(() => anchor.focus());
    hover(anchor);
    unhover(anchor);
    advance(CARD_CLOSE_DELAY_MS * 2);
    expect(card()).toHaveTextContent("Q00 drift");

    hover(anchor);
    act(() => anchor.blur());
    advance(CARD_CLOSE_DELAY_MS * 2);
    expect(card()).toHaveTextContent("Q00 drift");
    unhover(anchor);
    advance(CARD_CLOSE_DELAY_MS);
    expect(card()).toBeNull();
  });

  it("shows cards for explicit fragment links and links within diagrams", () => {
    const { container } = wrap(<ChatMarkdown>{"[details](#details)"}</ChatMarkdown>);
    hover(link("details"));
    advance(CARD_OPEN_DELAY_MS);
    expect(card()).toHaveTextContent("#details");

    const frame = document.createElement("div");
    frame.setAttribute("data-chat-mermaid", "");
    const diagramLink = document.createElement("a");
    diagramLink.href = "https://example.com/diagram";
    diagramLink.textContent = "diagram destination";
    frame.append(diagramLink);
    container.querySelector(".chat-prose")!.append(frame);
    unhover(link("details"), diagramLink);
    hover(diagramLink);
    expect(card()).toHaveTextContent("https://example.com/diagram");
  });

  it("ignores touch hovers", () => {
    wrap(<ChatMarkdown>{MARKDOWN}</ChatMarkdown>);
    fireEvent.pointerOver(link("the paper"), { pointerType: "touch" });
    advance(CARD_OPEN_DELAY_MS * 2);
    expect(card()).toBeNull();
  });

  it("keeps click previews and closes the card when a link is pressed", () => {
    wrap(<ChatMarkdown>{MARKDOWN}</ChatMarkdown>);
    hover(link("the Rabi result"));
    advance(CARD_OPEN_DELAY_MS);
    expect(card()).not.toBeNull();

    fireEvent.pointerDown(link("the Rabi result"), { pointerType: "mouse" });
    act(() => link("the Rabi result").focus());
    expect(card()).toBeNull();
    expect(fireEvent.click(link("the Rabi result"))).toBe(false);
    expect(screen.getByTestId("chat-link-preview")).toHaveTextContent("CheckRabi");
    expect(card()).toBeNull();
  });

  it("lets modified clicks and external links through to the browser", () => {
    wrap(<ChatMarkdown>{MARKDOWN}</ChatMarkdown>);
    hover(link("the run"));
    advance(CARD_OPEN_DELAY_MS);
    expect(fireEvent.click(link("the run"), { metaKey: true })).toBe(true);
    expect(card()).toBeNull();
    expect(screen.queryByTestId("chat-link-preview")).toBeNull();

    hover(link("the paper"));
    advance(CARD_OPEN_DELAY_MS);
    expect(fireEvent.click(link("the paper"))).toBe(true);
    expect(card()).toBeNull();
  });

  it("shows a card for a standalone chat link", () => {
    wrap(<ChatLink href="/forum/p1">Forum thread</ChatLink>);
    hover(link("Forum thread"));
    advance(CARD_OPEN_DELAY_MS);
    expect(card()).toHaveTextContent("Q00 drift");
    unhover(link("Forum thread"));
    advance(CARD_CLOSE_DELAY_MS);
    expect(card()).toBeNull();

    act(() => link("Forum thread").focus());
    expect(card()).toHaveTextContent("Q00 drift");
  });

  it("renders links without cards outside a preview provider", () => {
    render(<ChatMarkdown>{MARKDOWN}</ChatMarkdown>);
    hover(link("the paper"));
    advance(CARD_OPEN_DELAY_MS);
    expect(card()).toBeNull();
    expect(link("the paper")).toHaveAttribute("target", "_blank");
  });
});
