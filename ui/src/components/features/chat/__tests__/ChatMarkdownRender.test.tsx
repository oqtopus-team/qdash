import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatMarkdown } from "../ChatMarkdown";

const mermaid = vi.hoisted(() => ({
  initialize: vi.fn(),
  render: vi.fn(),
}));
vi.mock("mermaid", () => ({ default: mermaid }));

beforeAll(() => {
  // Streamdown renders a diagram once it scrolls into view.
  class VisibleObserver {
    constructor(private callback: IntersectionObserverCallback) {}
    observe(target: Element) {
      this.callback(
        [{ isIntersecting: true, target } as IntersectionObserverEntry],
        this as unknown as IntersectionObserver,
      );
    }
    unobserve() {}
    disconnect() {}
    takeRecords() {
      return [];
    }
  }
  globalThis.IntersectionObserver = VisibleObserver as unknown as typeof IntersectionObserver;
});

beforeEach(() => {
  mermaid.initialize.mockReset();
  mermaid.render.mockReset();
});

afterEach(cleanup);

describe("ChatMarkdown streaming", () => {
  it("completes unclosed Markdown while streaming and renders the finished text", () => {
    const { container, rerender } = render(
      <ChatMarkdown streaming>{"T1 is **stable and"}</ChatMarkdown>,
    );
    expect(container.querySelector("strong")).toHaveTextContent(/^stable and$/);
    expect(container).not.toHaveTextContent("**");

    rerender(
      <ChatMarkdown streaming>{"T1 is **stable** and [the run](/executions/e1"}</ChatMarkdown>,
    );
    // The link label shows, but nothing navigates until its URL has arrived.
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
    expect(container.querySelector("[data-incomplete]")).toHaveTextContent("the run");

    rerender(
      <ChatMarkdown streaming>
        {"T1 is **stable** and [the run](/executions/e1) passed."}
      </ChatMarkdown>,
    );
    expect(container.querySelector("strong")).toHaveTextContent(/^stable$/);
    expect(screen.getByRole("link", { name: "the run" })).toHaveAttribute("href", "/executions/e1");

    rerender(
      <ChatMarkdown>{"T1 is **stable** and [the run](/executions/e1) passed."}</ChatMarkdown>,
    );
    expect(container.querySelector("strong")).toHaveTextContent(/^stable$/);
    expect(container).toHaveTextContent("T1 is stable and the run passed.");
  });

  it("renders a saved answer as written, without completing it", () => {
    const { container } = render(<ChatMarkdown>{"5 * 3 and **unclosed"}</ChatMarkdown>);
    expect(container.querySelector("strong")).toBeNull();
    expect(container).toHaveTextContent("5 * 3 and **unclosed");
  });

  it("shows an open code fence as code with a caret, then as a finished block", () => {
    const partial = "Run:\n\n```python\nx = 2 ** 3  # **not bold\nprint(r'\\(x\\)')";
    const { container, rerender } = render(<ChatMarkdown streaming>{partial}</ChatMarkdown>);
    const code = container.querySelector("pre code");
    expect(code).toHaveTextContent("x = 2 ** 3 # **not bold");
    expect(code).toHaveTextContent("print(r'\\(x\\)')");
    expect(container.querySelector("strong")).toBeNull();
    expect(container.querySelector(".katex")).toBeNull();
    expect(container.querySelector("pre .animate-pulse")).not.toBeNull();

    rerender(<ChatMarkdown>{`${partial}\n\`\`\`\n`}</ChatMarkdown>);
    expect(container.querySelector("pre .animate-pulse")).toBeNull();
    expect(container.querySelector("pre code.hljs")).not.toBeNull();
    expect(screen.getByRole("button", { name: "Copy code" })).toBeInTheDocument();
    expect(screen.getByText("python")).toBeInTheDocument();
  });
});

describe("ChatMarkdown content", () => {
  it("renders inline and display math with KaTeX, including bracket delimiters", () => {
    const { container } = render(
      <ChatMarkdown>
        {"Decay \\(T_1 = 45\\,\\mu s\\) and $f$:\n\n\\[ y = e^{-t/T_1} \\]"}
      </ChatMarkdown>,
    );
    expect(container.querySelectorAll(".katex").length).toBeGreaterThanOrEqual(3);
    expect(container.querySelector(".katex-display")).not.toBeNull();
    expect(container).not.toHaveTextContent("\\(");
  });

  it("renders inline code and GFM tables in the chat styles", () => {
    const { container } = render(
      <ChatMarkdown>
        {"Use `qid`.\n\n| Qubit | T1 (us) |\n| --- | ---: |\n| Q03 | 42.1 |\n| Q04 | ~~n/a~~ |"}
      </ChatMarkdown>,
    );
    expect(container.querySelector("code.chat-inline-code")).toHaveTextContent("qid");
    const wrap = container.querySelector(".chat-table-wrap");
    expect(wrap).not.toBeNull();
    const table = within(wrap as HTMLElement).getByRole("table");
    expect(within(table).getByRole("columnheader", { name: "T1 (us)" })).toBeInTheDocument();
    expect(within(table).getByRole("cell", { name: "42.1" })).toBeInTheDocument();
    expect(table.querySelector("del")).toHaveTextContent("n/a");
  });

  it("keeps unsafe links and raw HTML inert", () => {
    const { container } = render(
      <ChatMarkdown>
        {"[click](javascript:alert(1)) <img src=x onerror=alert(1)> <script>alert(2)</script>"}
      </ChatMarkdown>,
    );
    expect(container.querySelector("script")).toBeNull();
    expect(container.querySelector("img")).toBeNull();
    expect(container).toHaveTextContent("<script>alert(2)</script>");
    expect(container).toHaveTextContent("click [blocked]");
    expect(container.querySelector("a")).toBeNull();
    expect(container.innerHTML).not.toMatch(/javascript:/i);
  });
});

describe("ChatMarkdown Mermaid diagrams", () => {
  const diagram =
    '```mermaid\ngraph TD\n  A[Rabi] --> B[T1]\n  click A href "https://example.com"\n```';

  it("waits for the fence to close before rendering a diagram", async () => {
    const partial = "```mermaid\ngraph TD\n  A[Rabi] --> B";
    const { container } = render(<ChatMarkdown streaming>{partial}</ChatMarkdown>);
    expect(container.querySelector("pre code")).toHaveTextContent("graph TD");
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(mermaid.render).not.toHaveBeenCalled();
  });

  it("renders a finished diagram in strict mode without navigable links", async () => {
    mermaid.render.mockResolvedValue({
      svg: '<svg viewBox="0 0 100 50"><a href="https://example.com" onclick="alert(1)"><text>Rabi</text></a></svg>',
    });
    render(<ChatMarkdown>{diagram}</ChatMarkdown>);

    const figure = await screen.findByRole("img", { name: "Mermaid chart" }, { timeout: 3000 });
    await waitFor(() => expect(figure).toHaveTextContent("Rabi"));
    const anchor = figure.querySelector("a");
    expect(anchor).not.toBeNull();
    expect(anchor).not.toHaveAttribute("href");
    expect(anchor).not.toHaveAttribute("onclick");

    expect(mermaid.initialize).toHaveBeenCalledWith(
      expect.objectContaining({ securityLevel: "strict", startOnLoad: false }),
    );
    expect(mermaid.render).toHaveBeenCalledWith(
      expect.any(String),
      expect.stringContaining("graph TD"),
    );
  });

  it("shows the source when a diagram cannot be parsed", async () => {
    mermaid.render.mockRejectedValue(new Error("Parse error on line 2"));
    render(<ChatMarkdown>{diagram}</ChatMarkdown>);

    const error = await screen.findByTestId("chat-mermaid-error", {}, { timeout: 3000 });
    expect(error).toHaveTextContent("Parse error on line 2");
    await waitFor(() => expect(error.querySelector("pre code")).toHaveTextContent("graph TD"));
  });
});
