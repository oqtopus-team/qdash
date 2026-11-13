import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatLinkPreviewProvider } from "../ChatLinkPreview";
import { ChatMarkdown } from "../ChatMarkdown";

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

afterEach(() => {
  cleanup();
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

const MARKDOWN = [
  "See [the Rabi result](http://localhost:3000/task-results/t1),",
  "[the run](/executions/20261006-012),",
  "[the thread](/forum/posts/p1) and [the paper](https://arxiv.org/abs/1).",
].join(" ");

describe("chat links", () => {
  it("previews a task result in a dialog with its figures and parameters", () => {
    useGetTaskResult.mockReturnValue({
      data: {
        data: {
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
        },
      },
    });
    wrap(<ChatMarkdown>{MARKDOWN}</ChatMarkdown>);

    const link = screen.getByRole("link", { name: "the Rabi result" });
    expect(link.getAttribute("target")).toBe("_blank");
    const click = fireEvent.click(link);
    expect(click).toBe(false); // default prevented: no navigation

    expect(useGetTaskResult).toHaveBeenCalledWith("t1", expect.anything());
    const dialog = screen.getByTestId("chat-link-preview");
    expect(dialog.textContent).toContain("CheckRabi");
    expect(dialog.textContent).toContain("rabi_frequency");
    expect(dialog.textContent).toContain("12.665 MHz");
    expect(screen.getByRole("img", { name: "CheckRabi_0" })).toBeTruthy();
    expect(screen.getByRole("link", { name: /Open page/ }).getAttribute("href")).toBe(
      "/task-results/t1",
    );
  });

  it("previews a legacy execution link and resolves its page from the chip", () => {
    useGetExecution.mockReturnValue({
      data: {
        data: { name: "pipeline-x", status: "running", chip_id: "64Qv3", note: {}, task: [] },
      },
    });
    wrap(<ChatMarkdown>{MARKDOWN}</ChatMarkdown>);

    fireEvent.click(screen.getByRole("link", { name: "the run" }));
    expect(screen.getByTestId("execution-progress")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Open page/ }).getAttribute("href")).toBe(
      "/execution/64Qv3/20261006-012",
    );
  });

  it("previews a forum post and sends the page link to the real route", () => {
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
    wrap(<ChatMarkdown>{MARKDOWN}</ChatMarkdown>);

    fireEvent.click(screen.getByRole("link", { name: "the thread" }));
    const dialog = screen.getByTestId("chat-link-preview");
    expect(dialog.textContent).toContain("Q00 drift");
    expect(dialog.textContent).toContain("T1 dropped");
    expect(screen.getByRole("link", { name: /Open page/ }).getAttribute("href")).toBe("/forum/p1");
  });

  it("lets external links and modified clicks through to the browser", () => {
    wrap(<ChatMarkdown>{MARKDOWN}</ChatMarkdown>);
    const external = screen.getByRole("link", { name: "the paper" });
    expect(external.getAttribute("target")).toBe("_blank");
    expect(fireEvent.click(external)).toBe(true);
    expect(screen.queryByTestId("chat-link-preview")).toBeNull();

    expect(fireEvent.click(screen.getByRole("link", { name: "the run" }), { ctrlKey: true })).toBe(
      true,
    );
    expect(screen.queryByTestId("chat-link-preview")).toBeNull();
  });
});
