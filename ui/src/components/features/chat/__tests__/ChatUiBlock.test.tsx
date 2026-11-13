import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatUiBlock } from "../ChatUiBlock";
import { messageText } from "../ChatMessages";

// Plotly is loaded with next/dynamic; a stand-in shows what it would draw and can fail on demand.
vi.mock("@/components/features/chat/ChatPlotlyChart", () => ({
  ChatPlotlyChart: ({ layout }: { layout: Record<string, unknown> }) => {
    if (layout.title === "boom") throw new Error("plot failed");
    return <div data-testid="plot">{String(layout.title ?? "")}</div>;
  },
}));

vi.mock("@/hooks/useCopilotChat", () => ({ answerFeedback: () => null }));

afterEach(cleanup);

const spec = {
  root: "s",
  elements: {
    s: { type: "Stack", props: {}, children: ["card", "table", "alert", "link"] },
    card: { type: "Card", props: { title: "Q03 coherence" }, children: ["t1"] },
    t1: {
      type: "Metric",
      props: { label: "T1", value: 42.1, unit: "us", detail: "exec 42", tone: "success" },
      children: [],
    },
    table: {
      type: "Table",
      props: {
        caption: "Latest",
        columns: [
          { key: "qid", label: "Qubit" },
          { key: "ok", label: "Passed", align: "right" },
        ],
        rows: [{ qid: "Q03", ok: true }, { qid: "Q04" }],
      },
      children: [],
    },
    alert: { type: "Alert", props: { tone: "error", message: "Q04 failed" }, children: [] },
    link: {
      type: "Link",
      props: { label: "Open Q03", href: "/chip/64Qv3/qubit/3" },
      children: [],
    },
  },
};

describe("ChatUiBlock", () => {
  it("renders the catalog components with DaisyUI and status text", () => {
    render(<ChatUiBlock ui={{ version: 1, spec, fallback: "fallback text" }} />);

    expect(screen.getByRole("heading", { name: "Q03 coherence" })).toBeInTheDocument();
    expect(screen.getByText("T1")).toBeInTheDocument();
    expect(screen.getByText("42.1")).toBeInTheDocument();
    expect(screen.getByText("us")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "OK" })).toBeInTheDocument();

    const table = screen.getByRole("table", { name: "Latest" });
    expect(within(table).getByRole("columnheader", { name: "Passed" })).toBeInTheDocument();
    expect(within(table).getByText("Yes")).toBeInTheDocument();
    expect(within(table).getByText("—")).toBeInTheDocument();

    expect(screen.getByText("Q04 failed")).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Error" })).toBeInTheDocument();

    const link = screen.getByRole("link", { name: "Open Q03" });
    expect(link).toHaveAttribute("href", "/chip/64Qv3/qubit/3");
    expect(screen.queryByText("fallback text")).not.toBeInTheDocument();
  });

  it("draws a chart element through the chat's Plotly chart", () => {
    render(
      <ChatUiBlock
        ui={{
          version: 1,
          spec: {
            root: "c",
            elements: {
              c: { type: "Chart", props: { data: [{ y: [1, 2] }], layout: { title: "T1 trend" } } },
            },
          },
          fallback: "[Chart: T1 trend]",
        }}
      />,
    );
    expect(screen.getByTestId("plot")).toHaveTextContent("T1 trend");
  });

  it("shows the fallback for an invalid spec, an unknown version, or an unsafe link", () => {
    const { unmount } = render(
      <ChatUiBlock ui={{ version: 1, spec: { root: "x", elements: {} }, fallback: "- T1: 42" }} />,
    );
    expect(screen.getByText("This view could not be displayed.")).toBeInTheDocument();
    expect(screen.getByRole("listitem")).toHaveTextContent("T1: 42");
    unmount();

    render(<ChatUiBlock ui={{ version: 99, spec, fallback: "newer view" }} />);
    expect(screen.queryByTestId("chat-ui-block")).not.toBeInTheDocument();
    expect(screen.getByText("newer view")).toBeInTheDocument();
    cleanup();

    const unsafe = {
      root: "l",
      elements: { l: { type: "Link", props: { label: "Evil", href: "https://evil.example" } } },
    };
    render(<ChatUiBlock ui={{ version: 1, spec: unsafe, fallback: "Evil" }} />);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("shows the fallback instead of dropping an element that fails to render", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <ChatUiBlock
        ui={{
          version: 1,
          spec: {
            root: "c",
            elements: {
              c: { type: "Chart", props: { data: [{ y: [1] }], layout: { title: "boom" } } },
            },
          },
          fallback: "[Chart: boom]",
        }}
      />,
    );
    expect(screen.getByText("This view could not be displayed.")).toBeInTheDocument();
    expect(screen.getByText("[Chart: boom]")).toBeInTheDocument();
  });

  it("copies a message's text with each UI's fallback in place", () => {
    const content = JSON.stringify({
      blocks: [
        {
          type: "ui",
          content: "- T1: 42 us",
          chart: null,
          ui: { version: 1, spec, fallback: "- T1: 42 us" },
        },
        { type: "chart", content: null, chart: { data: [], layout: {} } },
        { type: "text", content: "T1 is healthy.", chart: null },
      ],
      assessment: null,
    });
    expect(messageText(content)).toBe("- T1: 42 us\n\nT1 is healthy.");
    expect(messageText("plain answer")).toBe("plain answer");
  });
});
