import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TaskResultThreads, newThreadHref } from "../TaskResultThreads";

const listForumPosts = vi.fn();
vi.mock("@/client/forum/forum", () => ({
  useListForumPosts: (...args: unknown[]) => listForumPosts(...args),
}));
vi.mock("@/contexts/ProjectContext", () => ({ useProject: () => ({ canEdit: true }) }));

afterEach(() => {
  cleanup();
  listForumPosts.mockReset();
});

describe("newThreadHref", () => {
  it("prefills the task result, its target, and a title", () => {
    const href = newThreadHref({
      taskId: "t1",
      taskName: "CheckRabi",
      chipId: "64Qv3",
      qid: "4-6",
    });
    const params = new URL(`http://x${href}`).searchParams;
    expect(href.startsWith("/forum/new?")).toBe(true);
    expect(params.get("task_id")).toBe("t1");
    expect(params.get("category")).toBe("coupling");
    expect(params.get("target_type")).toBe("coupling");
    expect(params.get("target_id")).toBe("4-6");
    expect(params.get("chip_id")).toBe("64Qv3");
    expect(params.get("title")).toBe("CheckRabi on 4-6");
  });
});

describe("TaskResultThreads", () => {
  it("lists every thread about the result and offers a new one", () => {
    listForumPosts.mockReturnValue({
      data: {
        data: {
          posts: [
            {
              id: "p1",
              number: 12,
              title: "ZX90 fidelity looks off",
              status: "resolved",
              reply_count: 3,
              updated_at: new Date().toISOString(),
            },
          ],
        },
      },
      isLoading: false,
    });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <TaskResultThreads taskId="t1" taskName="CheckRabi" chipId="64Qv3" qid="4-6" />
      </QueryClientProvider>,
    );
    expect(listForumPosts).toHaveBeenCalledWith(
      { task_id: "t1", status: "all", limit: 20 },
      expect.anything(),
    );
    expect(screen.getByText("ZX90 fidelity looks off").closest("a")?.getAttribute("href")).toBe(
      "/forum/p1",
    );
    expect(screen.getByText("Resolved")).toBeTruthy();
    expect(screen.getByText("New thread").closest("a")?.getAttribute("href")).toContain(
      "task_id=t1",
    );
  });

  it("explains when nothing is linked yet", () => {
    listForumPosts.mockReturnValue({ data: { data: { posts: [] } }, isLoading: false });
    render(
      <QueryClientProvider client={new QueryClient()}>
        <TaskResultThreads taskId="t1" taskName="CheckRabi" chipId={null} qid="0" />
      </QueryClientProvider>,
    );
    expect(screen.getByText(/No forum thread is about this result yet/)).toBeTruthy();
  });
});
