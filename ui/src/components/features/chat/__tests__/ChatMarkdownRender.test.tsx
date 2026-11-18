import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resetMermaidCache } from "@/lib/chatMermaid";
import { ChatMarkdown } from "../ChatMarkdown";

const mermaid = vi.hoisted(() => ({
  initialize: vi.fn(),
  render: vi.fn(),
}));
vi.mock("mermaid", () => ({ default: mermaid }));

const theme = vi.hoisted(() => ({ dark: false }));
vi.mock("@/contexts/ThemeContext", () => ({
  useIsDarkTheme: () => theme.dark,
}));

const copyText = vi.hoisted(() => vi.fn());
vi.mock("@/lib/utils/clipboard", () => ({ copyText }));

beforeEach(() => {
  mermaid.initialize.mockReset();
  mermaid.render.mockReset();
  copyText.mockReset();
  copyText.mockResolvedValue(undefined);
  theme.dark = false;
  resetMermaidCache();
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
    expect(container.querySelector('pre [data-markdown="caret"]')).not.toBeNull();

    rerender(<ChatMarkdown>{`${partial}\n\`\`\`\n`}</ChatMarkdown>);
    expect(container.querySelector('[data-markdown="caret"]')).toBeNull();
    expect(container.querySelector("pre code .hljs-comment")).toHaveTextContent("# **not bold");
    expect(screen.getByRole("button", { name: "Copy code" })).toBeEnabled();
    expect(screen.getByText("python")).toBeInTheDocument();
  });

  it("keeps finished blocks in place while later text streams in", () => {
    const first = "Intro **bold** paragraph.\n\nSecond paragraph";
    const { container, rerender } = render(<ChatMarkdown streaming>{first}</ChatMarkdown>);
    const intro = container.querySelector("p");
    rerender(<ChatMarkdown streaming>{`${first} keeps growing`}</ChatMarkdown>);
    rerender(<ChatMarkdown streaming>{`${first} keeps growing.\n\n- a list`}</ChatMarkdown>);
    // The completed paragraph is the same DOM node, not a re-render.
    expect(container.querySelector("p")).toBe(intro);
    expect(container.querySelector("li")).toHaveTextContent("a list");
  });

  it("renders Japanese emphasis next to CJK punctuation", () => {
    const { container } = render(
      <ChatMarkdown>{"**重要。**キャリブレーションは「**完了**」しました。"}</ChatMarkdown>,
    );
    const strong = container.querySelectorAll("strong");
    expect(strong).toHaveLength(2);
    expect(strong[0]).toHaveTextContent(/^重要。$/);
    expect(strong[1]).toHaveTextContent(/^完了$/);
    expect(container).not.toHaveTextContent("**");
  });

  it("copies code with the shared clipboard helper", async () => {
    render(<ChatMarkdown>{"```bash\nqdash run\n```"}</ChatMarkdown>);
    const button = screen.getByRole("button", { name: "Copy code" });
    fireEvent.click(button);
    expect(copyText).toHaveBeenCalledWith("qdash run\n");
    await waitFor(() => expect(button).toHaveTextContent("Copied"));
    expect(screen.queryByRole("button", { name: /download/i })).toBeNull();
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

  it("preserves TeX source and decoded entities through the Words math hook", () => {
    const formulas = [
      String.raw`a < b > c`,
      String.raw`\text{A\&B "quoted"}`,
      String.raw`\frac{1}{\sqrt{2}}`,
    ];
    const { container } = render(
      <ChatMarkdown>{formulas.map((tex) => `$${tex}$`).join("\n\n")}</ChatMarkdown>,
    );
    expect(
      Array.from(
        container.querySelectorAll('annotation[encoding="application/x-tex"]'),
        (node) => node.textContent,
      ),
    ).toEqual(formulas);
    expect(container.querySelector(".katex-error")).toBeNull();
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
    expect(container).toHaveTextContent("<img src=x onerror=alert(1)>");
    expect(container.querySelector('[data-markdown="blocked-link"]')).toHaveTextContent("click");
    expect(container.querySelector("a")).toBeNull();
    expect(container.innerHTML).not.toMatch(/javascript:/i);
  });

  it("shows block HTML as text and leaves code, math and autolinks alone", () => {
    const { container } = render(
      <ChatMarkdown>
        {[
          "<details>\n<summary>Fit</summary>\nT1 = 42 us\n</details>",
          'Use `<qubit id="Q0">` when $a<b$, see <https://qdash.example/docs>.',
          '```xml\n<chip id="64Qv3"/>\n```',
        ].join("\n\n")}
      </ChatMarkdown>,
    );
    expect(container.querySelector("details")).toBeNull();
    expect(container).toHaveTextContent("<details> <summary>Fit</summary> T1 = 42 us </details>");
    expect(container.querySelector("code.chat-inline-code")).toHaveTextContent(/^<qubit id="Q0">$/);
    expect(container.querySelector(".katex")).not.toBeNull();
    expect(container.querySelector("pre code")).toHaveTextContent(/^<chip id="64Qv3"\/>$/);
    expect(screen.getByRole("link", { name: "https://qdash.example/docs" })).toHaveAttribute(
      "target",
      "_blank",
    );
    expect(container).not.toHaveTextContent("\\<");
  });
});

describe("ChatMarkdown Mermaid diagrams", () => {
  it("retains all diagrams after the shared cache evicts earlier results", async () => {
    mermaid.render.mockImplementation(async (_id: string, source: string) => ({
      svg: `<svg><text>${source}</text></svg>`,
    }));
    const source = Array.from(
      { length: 201 },
      (_, i) => `\`\`\`mermaid\ngraph TD\n A${i}-->B${i}\n\`\`\``,
    ).join("\n\n");
    const { container, rerender } = render(<ChatMarkdown>{source}</ChatMarkdown>);
    await waitFor(
      () => expect(container.querySelectorAll('[data-chat-mermaid="ready"]')).toHaveLength(201),
      { timeout: 15000 },
    );
    rerender(<ChatMarkdown>{`${source}\n\nFinished.`}</ChatMarkdown>);
    expect(container.querySelectorAll('[data-chat-mermaid="ready"]')).toHaveLength(201);
    expect(mermaid.render).toHaveBeenCalledTimes(201);
  }, 20000);

  const SVG = '<svg viewBox="0 0 100 50"><text>Rabi</text></svg>';

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
    expect(within(error).getByRole("button", { name: "Copy code" })).toBeInTheDocument();
  });

  it("zooms inline, opens fullscreen and copies the source", async () => {
    mermaid.render.mockResolvedValue({ svg: SVG });
    render(<ChatMarkdown>{diagram}</ChatMarkdown>);
    const figure = await screen.findByRole("img", { name: "Mermaid chart" });
    const canvas = figure.querySelector<HTMLElement>("[data-mermaid-canvas]");

    fireEvent.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(canvas?.style.transform).toContain("scale(1.25)");
    expect(figure).toHaveAttribute("data-zoomed");
    fireEvent.click(screen.getByRole("button", { name: "Reset view" }));
    expect(canvas?.style.transform).toBe("");

    fireEvent.click(screen.getByRole("button", { name: "Copy diagram source" }));
    expect(copyText).toHaveBeenCalledWith(expect.stringContaining("A[Rabi] --> B[T1]"));

    fireEvent.click(screen.getByRole("button", { name: "Open fullscreen" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByTestId("chat-mermaid-fullscreen")).toHaveTextContent("Rabi");
    fireEvent.click(within(dialog).getByRole("button", { name: "Close" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("renders diagrams in the dark Mermaid theme on dark themes", async () => {
    theme.dark = true;
    mermaid.render.mockResolvedValue({ svg: SVG });
    render(<ChatMarkdown>{diagram}</ChatMarkdown>);
    await screen.findByRole("img", { name: "Mermaid chart" });
    expect(mermaid.initialize).toHaveBeenCalledWith(
      expect.objectContaining({ theme: "dark", securityLevel: "strict" }),
    );
  });
});
