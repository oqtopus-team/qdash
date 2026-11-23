import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AxiosError, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AXIOS_INSTANCE } from "@/lib/api/custom-instance";

import { TaskResultsPageContent } from "../TaskResultsPageContent";

// The task result list comes from the generated hook over a faked network, with a real
// QueryClient, so loading, error and refetch states follow TanStack Query.
const nav = vi.hoisted(() => ({ params: new URLSearchParams() }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/task-results",
  useSearchParams: () => nav.params,
}));
vi.mock("@/client/task-file/task-file", () => ({
  useGetTaskFileSettings: () => ({ data: undefined }),
  useListTaskInfo: () => ({ data: { data: { tasks: [] } } }),
}));
vi.mock("@/client/execution/execution", () => ({
  useListExecutions: () => ({ data: undefined, isLoading: false }),
}));
vi.mock("@/components/selectors/ChipSelector", () => ({ ChipSelector: () => null }));
vi.mock("@/components/selectors/TaskSelector", () => ({ TaskSelector: () => null }));
vi.mock("@/components/features/task-results/TaskResultPreviewSidebar", async (importOriginal) => {
  const actual =
    await importOriginal<
      typeof import("@/components/features/task-results/TaskResultPreviewSidebar")
    >();
  return { ...actual, TaskResultPreviewSidebar: () => null };
});

type Reply = "error" | Promise<"error" | unknown> | unknown;
let listReply: (params: Record<string, unknown>) => Reply;
const listRequests: Record<string, unknown>[] = [];
const originalAdapter = AXIOS_INSTANCE.defaults.adapter;

const page = (taskName: string) => ({
  items: [
    {
      task_id: `task-${taskName}`,
      task_name: taskName,
      status: "failed",
      qid: "12",
      chip_id: "64Q",
      execution_id: "20261031-003",
      username: "admin",
      start_at: "2026-10-31T10:00:00Z",
      elapsed_time: "12s",
      message: "Fit did not converge",
      has_stack_trace: false,
    },
  ],
  total: 1,
  skip: 0,
  limit: 50,
  status_counts: { failed: 1, completed: 0, running: 0, cancelled: 0 },
});

const fakeAdapter: AxiosAdapter = async (config: InternalAxiosRequestConfig) => {
  const params = { ...(config.params as Record<string, unknown>) };
  listRequests.push(params);
  let answer = listReply(params);
  if (answer instanceof Promise) answer = await answer;
  if (answer === "error") {
    throw new AxiosError("Request failed", "ERR_BAD_RESPONSE", config, null, {
      data: { detail: "boom" },
      status: 500,
      statusText: "Internal Server Error",
      headers: {},
      config,
    });
  }
  return { data: answer, status: 200, statusText: "OK", headers: {}, config };
};

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const tree = () => (
    <QueryClientProvider client={client}>
      <TaskResultsPageContent />
    </QueryClientProvider>
  );
  const view = render(tree());
  return { client, rerender: () => view.rerender(tree()) };
}

/** A reply held until the test releases it. */
function held<T>() {
  let release: (value: T) => void = () => undefined;
  const promise = new Promise<T>((resolve) => (release = resolve));
  return { promise, release: (value: T) => release(value) };
}

beforeEach(() => {
  AXIOS_INSTANCE.defaults.adapter = fakeAdapter;
  nav.params = new URLSearchParams();
  listReply = () => page("CheckRabi");
  listRequests.length = 0;
});

afterEach(() => {
  cleanup();
  AXIOS_INSTANCE.defaults.adapter = originalAdapter;
});

describe("TaskResultsPageContent failures", () => {
  it("retries a failed first load in place", async () => {
    listReply = () => "error";
    setup();
    expect(await screen.findByText("Could not load task results")).toBeInTheDocument();

    const reply = held<unknown>();
    listReply = () => reply.promise;
    fireEvent.click(screen.getByRole("button", { name: "Try Again" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Try Again" })).toBeDisabled());
    expect(screen.getByText("Could not load task results")).toBeInTheDocument();

    await act(async () => reply.release(page("CheckT1")));
    expect(await screen.findByText("CheckT1")).toBeInTheDocument();
    expect(screen.queryByText("Could not load task results")).not.toBeInTheDocument();
  });

  it("keeps the loaded results when a background refetch fails", async () => {
    const { client } = setup();
    expect(await screen.findByText("CheckRabi")).toBeInTheDocument();

    listReply = () => "error";
    await act(async () => {
      await client.refetchQueries();
    });
    expect(await screen.findByText(/Could not refresh task results/)).toBeInTheDocument();
    expect(screen.getByText("CheckRabi")).toBeInTheDocument();

    const reply = held<unknown>();
    listReply = () => reply.promise;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Retry" })).toBeDisabled());
    await act(async () => reply.release(page("CheckT1")));
    expect(await screen.findByText("CheckT1")).toBeInTheDocument();
    expect(screen.queryByText(/Could not refresh task results/)).not.toBeInTheDocument();
  });

  it("does not show results of the previous filters after the filters change", async () => {
    const { client, rerender } = setup();
    expect(await screen.findByText("CheckRabi")).toBeInTheDocument();
    listReply = () => "error";
    await act(async () => {
      await client.refetchQueries();
    });
    expect(await screen.findByText(/Could not refresh task results/)).toBeInTheDocument();

    // A new filter is its own query: its first-load error shows, not the old rows or warning.
    nav.params = new URLSearchParams("status=completed");
    rerender();
    expect(await screen.findByText("Could not load task results")).toBeInTheDocument();
    expect(screen.queryByText("CheckRabi")).not.toBeInTheDocument();
    expect(screen.queryByText(/Could not refresh task results/)).not.toBeInTheDocument();
    expect(listRequests[listRequests.length - 1]).toMatchObject({ status: "completed" });
  });
});
