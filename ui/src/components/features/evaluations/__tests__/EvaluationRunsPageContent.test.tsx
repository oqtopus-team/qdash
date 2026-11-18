import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { AxiosError, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { NuqsTestingAdapter, type UrlUpdateEvent } from "nuqs/adapters/testing";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AXIOS_INSTANCE } from "@/lib/api/custom-instance";
import type { EvaluationRunSummary } from "@/schemas";

import { EvaluationRunsPageContent } from "../EvaluationRunsPageContent";

const last = <T,>(items: readonly T[]): T | undefined => items[items.length - 1];

// The generated list hook and a real QueryClient decide what is shown; only the network adapter
// is faked, so loading, error and refetch states follow TanStack Query itself.
const mocks = vi.hoisted(() => ({ projectId: "project-a" as string | null }));
vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ projectId: mocks.projectId }),
}));
vi.mock("@/client/task-file/task-file", () => ({
  useGetTaskFileSettings: () => ({ data: undefined }),
  useListTaskInfo: () => ({ data: { data: { tasks: [] } } }),
}));
vi.mock("@/components/selectors/ChipSelector", () => ({
  ChipSelector: ({ onChipSelect }: { onChipSelect: (chip: string) => void }) => (
    <button type="button" onClick={() => onChipSelect("64Qv2")}>
      Pick chip 64Qv2
    </button>
  ),
}));
vi.mock("@/components/selectors/TaskSelector", () => ({
  TaskSelector: ({ onTaskSelect }: { onTaskSelect: (task: string) => void }) => (
    <button type="button" onClick={() => onTaskSelect("CheckRabi")}>
      Pick task CheckRabi
    </button>
  ),
}));

function run(index: number, override: Partial<EvaluationRunSummary> = {}): EvaluationRunSummary {
  return {
    run_id: `evr_${index}`,
    chip_id: "64Qv1",
    task_name: `Task${index}`,
    entity_type: "qubit",
    trigger: "bulk",
    mode: "direct",
    with_examples: false,
    requested_by: "alice",
    requested_at: "2026-10-11T07:00:00Z",
    status: "completed",
    total: 2,
    completed_count: 2,
    failed_count: 0,
    pending_count: 0,
    parsed_count: 2,
    complete_count: 2,
    duration_ms_total: 60_000,
    success_count: 2,
    agree_count: 0,
    disagree_count: 0,
    model: "model",
    ...override,
  };
}

const runs = (count: number) => Array.from({ length: count }, (_, index) => run(index + 1));

type Reply = { runs: EvaluationRunSummary[] } | "error" | Promise<"error" | EvaluationRunSummary[]>;
let reply: (params: Record<string, unknown>) => Reply;
const requests: Record<string, unknown>[] = [];
const originalAdapter = AXIOS_INSTANCE.defaults.adapter;

const fakeAdapter: AxiosAdapter = async (config: InternalAxiosRequestConfig) => {
  const params = { ...(config.params as Record<string, unknown>) };
  requests.push(params);
  let answer = reply(params);
  if (answer instanceof Promise) {
    const settled = await answer;
    answer = settled === "error" ? "error" : { runs: settled };
  }
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

function setup(searchParams = "") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onUrlUpdate = vi.fn<(event: UrlUpdateEvent) => void>();
  const view = render(
    <QueryClientProvider client={client}>
      <NuqsTestingAdapter searchParams={searchParams} onUrlUpdate={onUrlUpdate} hasMemory>
        <EvaluationRunsPageContent />
      </NuqsTestingAdapter>
    </QueryClientProvider>,
  );
  return { ...view, client, onUrlUpdate };
}

const lastUrl = (onUrlUpdate: ReturnType<typeof setup>["onUrlUpdate"]) =>
  last(onUrlUpdate.mock.calls)?.[0];

beforeEach(() => {
  AXIOS_INSTANCE.defaults.adapter = fakeAdapter;
  requests.length = 0;
  mocks.projectId = "project-a";
  reply = () => ({ runs: runs(30) });
});

afterEach(() => {
  cleanup();
  AXIOS_INSTANCE.defaults.adapter = originalAdapter;
});

describe("EvaluationRunsPageContent filters and pages", () => {
  it("restores chip, task and page from the URL and requests the newest runs up to that page", async () => {
    reply = () => ({ runs: runs(60) });
    setup("chip=64Qv1&task=CheckT1&page=2");

    expect(await screen.findByText("Task26")).toBeInTheDocument();
    expect(screen.queryByText("Task25")).not.toBeInTheDocument();
    expect(last(requests)).toEqual({ chip_id: "64Qv1", task: "CheckT1", limit: 51 });
    expect(screen.getByText("Runs 26-50")).toBeInTheDocument();
    expect(screen.getByText("Page 2")).toBeInTheDocument();
  });

  it("moves between pages with history entries and returns to page 1 on a filter change", async () => {
    reply = (params) => ({ runs: runs(Number(params.limit)) });
    const { onUrlUpdate } = setup();
    await screen.findByText("Task1");
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("Task26")).toBeInTheDocument();
    expect(last(requests)).toMatchObject({ limit: 51 });
    await waitFor(() =>
      expect(lastUrl(onUrlUpdate)).toMatchObject({
        queryString: "?page=2",
        options: { history: "push" },
      }),
    );

    fireEvent.click(screen.getByRole("button", { name: "Pick chip 64Qv2" }));
    await waitFor(() => expect(lastUrl(onUrlUpdate)?.queryString).toBe("?chip=64Qv2"));
    await waitFor(() => expect(last(requests)).toEqual({ chip_id: "64Qv2", limit: 26 }));
  });

  it("treats an invalid page as the first page", async () => {
    setup("page=abc");
    await screen.findByText("Task1");
    expect(last(requests)).toEqual({ limit: 26 });
  });

  it("corrects a page past the end to the last page with runs without a history entry", async () => {
    const { onUrlUpdate } = setup("page=5");

    await waitFor(() =>
      expect(lastUrl(onUrlUpdate)).toMatchObject({
        queryString: "?page=2",
        options: { history: "replace" },
      }),
    );
    expect(await screen.findByText("Task30")).toBeInTheDocument();
    expect(last(requests)).toEqual({ limit: 51 });
  });

  it("shows an empty state for the filters with a way to clear them", async () => {
    reply = (params) => ({ runs: params.chip_id ? [] : runs(3) });
    const { onUrlUpdate } = setup("chip=missing");

    expect(await screen.findByText("No evaluation runs match these filters")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
    await waitFor(() => expect(lastUrl(onUrlUpdate)?.queryString).toBe(""));
    expect(await screen.findByText("Task3")).toBeInTheDocument();
  });
});

describe("EvaluationRunsPageContent comparison picks", () => {
  it("keeps a pick listed in the compare bar while another page is shown", async () => {
    reply = (params) => ({ runs: runs(Number(params.limit)) });
    setup();
    fireEvent.click(await screen.findByLabelText(/Compare Task1 run/));

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByText("Task26");
    const bar = screen.getByTestId("compare-bar");
    expect(within(bar).getByText(/Task1 \(/)).toBeInTheDocument();
    expect(within(bar).getByText("1")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText(/Compare Task26 run/));
    expect(within(bar).getByRole("link", { name: /Compare/ })).toHaveAttribute(
      "href",
      expect.stringContaining("evr_1"),
    );

    fireEvent.click(within(bar).getByRole("button", { name: /Remove Task1/ }));
    expect(within(bar).queryByText(/Task1 \(/)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Compare Task26 run/)).toBeChecked();
  });

  it("drops picks made in another project", async () => {
    const { rerender, client } = setup();
    fireEvent.click(await screen.findByLabelText(/Compare Task1 run/));
    expect(screen.getByTestId("compare-bar")).toBeInTheDocument();

    mocks.projectId = "project-b";
    rerender(
      <QueryClientProvider client={client}>
        <NuqsTestingAdapter hasMemory>
          <EvaluationRunsPageContent />
        </NuqsTestingAdapter>
      </QueryClientProvider>,
    );
    expect(screen.queryByTestId("compare-bar")).not.toBeInTheDocument();
    mocks.projectId = "project-a";
    rerender(
      <QueryClientProvider client={client}>
        <NuqsTestingAdapter hasMemory>
          <EvaluationRunsPageContent />
        </NuqsTestingAdapter>
      </QueryClientProvider>,
    );
    expect(screen.queryByTestId("compare-bar")).not.toBeInTheDocument();
    expect(screen.getByLabelText(/Compare Task1 run/)).not.toBeChecked();
  });
});

describe("EvaluationRunsPageContent failures", () => {
  it("retries a failed first load in place and disables the retry while it runs", async () => {
    reply = () => "error";
    setup();

    const retry = await screen.findByRole("button", { name: "Try Again" });
    expect(screen.getByText("Could not load evaluation runs")).toBeInTheDocument();

    let release: (value: EvaluationRunSummary[]) => void = () => undefined;
    reply = () => new Promise((resolve) => (release = resolve));
    fireEvent.click(retry);
    await waitFor(() => expect(screen.getByRole("button", { name: "Try Again" })).toBeDisabled());

    await act(async () => release(runs(2)));
    expect(await screen.findByText("Task2")).toBeInTheDocument();
    expect(screen.queryByText("Could not load evaluation runs")).not.toBeInTheDocument();
  });

  it("keeps the loaded runs when a background refetch fails and offers a retry", async () => {
    const { client } = setup();
    await screen.findByText("Task1");

    reply = () => "error";
    await act(async () => {
      await client.refetchQueries();
    });
    expect(await screen.findByText(/Could not refresh evaluation runs/)).toBeInTheDocument();
    expect(screen.getByText("Task1")).toBeInTheDocument();

    reply = () => ({ runs: [run(1, { task_name: "Fresh" })] });
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText("Fresh")).toBeInTheDocument();
    expect(screen.queryByText(/Could not refresh evaluation runs/)).not.toBeInTheDocument();
  });
});
