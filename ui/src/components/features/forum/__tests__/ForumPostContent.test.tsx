import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ForumPostContent } from "../ForumPostContent";

const getTaskResult = vi.fn();
vi.mock("@/client/task/task", () => ({
  useGetTaskResult: (...args: unknown[]) => getTaskResult(...args),
}));
vi.mock("@/components/charts/TaskFigure", () => ({ TaskFigure: () => <div>figure</div> }));

afterEach(() => {
  cleanup();
  getTaskResult.mockReset();
});

describe("ForumPostContent", () => {
  it("shows the task result a thread is about before the text, once", () => {
    getTaskResult.mockReturnValue({
      data: {
        data: {
          task_name: "CheckRabi",
          status: "completed",
          qid: "5",
          chip_id: "64Qv3",
          end_at: null,
          figure_path: [],
          json_figure_path: [],
        },
      },
      isLoading: false,
      isError: false,
    });
    render(
      <ForumPostContent
        content="See /task-results/t1 and /task-results/t2"
        contentBlocks={[]}
        aboutTaskId="t1"
      />,
    );
    expect(screen.getByText("About this task result")).toBeTruthy();
    expect(screen.getByText("Linked task results")).toBeTruthy();
    // t1 is the thread's own result; the content link to it is not repeated.
    expect(getTaskResult.mock.calls.map((call) => call[0])).toEqual(["t1", "t2"]);
    expect(screen.getAllByText("CheckRabi").length).toBe(2);
  });
});
