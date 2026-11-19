import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatMarkdown } from "@/components/features/chat/ChatMarkdown";
import { resetMermaidCache } from "@/lib/chatMermaid";
import { MarkdownContent } from "../MarkdownContent";

const mermaid = vi.hoisted(() => ({
  rendering: 0,
  overlapped: false,
  initialize: vi.fn(),
  render: vi.fn(),
}));
vi.mock("mermaid", () => ({ default: mermaid }));
vi.mock("@/contexts/ThemeContext", () => ({ useIsDarkTheme: () => false }));

const NOTE = '```mermaid\ngraph TD\n  N1[Note] --> N2\n  click N1 href "https://example.com"\n```';
const ANSWER = "```mermaid\ngraph TD\n  C1[Answer] --> C2\n```";

beforeEach(() => {
  resetMermaidCache();
  mermaid.rendering = 0;
  mermaid.overlapped = false;
  mermaid.initialize.mockReset();
  mermaid.render.mockReset();
  mermaid.render.mockImplementation(async (_id: string, source: string) => {
    if (mermaid.rendering > 0) mermaid.overlapped = true;
    mermaid.rendering += 1;
    await new Promise((resolve) => setTimeout(resolve, 5));
    mermaid.rendering -= 1;
    const label = source.includes("Note") ? "Note" : "Answer";
    return {
      svg: `<svg viewBox="0 0 10 10"><a href="https://example.com" onclick="alert(1)"><text>${label}</text></a></svg>`,
    };
  });
});

afterEach(cleanup);

describe("MarkdownContent Mermaid diagrams", () => {
  it("renders through the shared strict renderer, keeping sanitized links", async () => {
    const { container } = render(<MarkdownContent content={NOTE} />);

    await waitFor(() => expect(container.querySelector("svg")).toHaveTextContent("Note"));
    const anchor = container.querySelector("svg a");
    expect(anchor).toHaveAttribute("href", "https://example.com");
    expect(anchor).not.toHaveAttribute("onclick");
    expect(mermaid.initialize).toHaveBeenCalledWith(
      expect.objectContaining({ theme: "default", securityLevel: "strict" }),
    );
  });

  it("shows the source when the diagram cannot be rendered", async () => {
    mermaid.render.mockRejectedValue(new Error("Parse error"));
    const { container } = render(<MarkdownContent content={NOTE} />);
    await waitFor(() => expect(container).toHaveTextContent("N1[Note] --> N2"));
    expect(container.querySelector("svg")).toBeNull();
  });

  it("never leaves chat with a loose config when both render on one page", async () => {
    render(
      <>
        <div data-testid="note-a">
          <MarkdownContent content={NOTE} />
        </div>
        <ChatMarkdown>{ANSWER}</ChatMarkdown>
        <div data-testid="note-b">
          <MarkdownContent content={NOTE.replace("N2", "N3")} />
        </div>
      </>,
    );

    const figure = await screen.findByRole("img", { name: "Mermaid chart" }, { timeout: 3000 });
    await waitFor(() => expect(figure).toHaveTextContent("Answer"));
    await waitFor(() => expect(mermaid.render).toHaveBeenCalledTimes(3));
    for (const note of ["note-a", "note-b"]) {
      await waitFor(() => expect(screen.getByTestId(note)).toHaveTextContent("Note"));
    }

    expect(mermaid.overlapped).toBe(false);
    expect(mermaid.initialize).toHaveBeenCalledTimes(3);
    for (const [config] of mermaid.initialize.mock.calls) {
      expect(config).toMatchObject({ securityLevel: "strict" });
    }
    // Each render runs right after the initialize for its own consumer.
    const order = [
      ...mermaid.initialize.mock.calls.map(([config], i) => ({
        at: mermaid.initialize.mock.invocationCallOrder[i],
        what: (config as { theme: string }).theme,
      })),
      ...mermaid.render.mock.calls.map(([, source], i) => ({
        at: mermaid.render.mock.invocationCallOrder[i],
        what: String(source).includes("Note") ? "render note" : "render answer",
      })),
    ]
      .sort((a, b) => a.at - b.at)
      .map((call) => call.what);
    const pairs = Array.from({ length: order.length / 2 }, (_, k) => order.slice(2 * k, 2 * k + 2));
    expect(pairs).toHaveLength(3);
    for (const pair of pairs) {
      expect([
        ["default", "render note"],
        ["neutral", "render answer"],
      ]).toContainEqual(pair);
    }
    expect(figure.querySelector("a")).not.toHaveAttribute("href");
  });
});
