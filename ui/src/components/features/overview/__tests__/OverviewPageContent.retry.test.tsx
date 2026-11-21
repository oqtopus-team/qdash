import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AxiosError, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AXIOS_INSTANCE } from "@/lib/api/custom-instance";

import { OverviewPageContent } from "../OverviewPageContent";

// The metrics configuration and chip metrics come from the generated hooks over a faked network,
// with a real QueryClient, so loading, error and refetch states follow TanStack Query. Other
// data, selectors and grids are reduced to what the assertions read.
const urlState = vi.hoisted(() => ({ chip: "chip-1" }));

vi.mock("@/client/chip/chip", () => ({
  useListChips: () => ({ data: { data: { chips: [{ chip_id: "chip-1" }] } }, isLoading: false }),
  useGetChip: () => ({ data: { data: { chip_id: urlState.chip, size: 1, note: null } } }),
}));
vi.mock("@/client/cooldown/cooldown", () => ({
  useListCooldowns: () => ({ data: { data: { cooldowns: [] } } }),
}));
vi.mock("@/client/forum/forum", () => ({
  getListForumLabelsQueryKey: () => ["/forum/labels"],
  useListForumPosts: () => ({ data: { data: { posts: [], total: 0, skip: 0, limit: 200 } } }),
  useListForumLabels: () => ({ data: { data: { labels: [] } }, isLoading: false, isError: false }),
}));
vi.mock("@/client/note/note", () => ({
  useGetChipNotesSummary: () => ({ data: { data: { qubits: [], couplings: [], task_notes: [] } } }),
}));
vi.mock("@/client/projects/projects", () => ({
  useListProjectMembers: () => ({ data: { data: { members: [] } } }),
}));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: { username: "tester" } }) }));
vi.mock("@/contexts/ProjectContext", () => ({ useProject: () => ({ projectId: "project-1" }) }));
vi.mock("@/hooks/useMetricsQueryParams", () => ({
  useMetricsQueryParams: () => ({
    queryParams: {
      selection_mode: "latest",
      start_at: "2026-06-01T00:00:00Z",
      end_at: "2026-06-08T00:00:00Z",
    },
    canFetch: true,
  }),
}));
vi.mock("@/hooks/useUrlState", () => ({
  useMetricsUrlState: () => ({
    selectedChip: urlState.chip,
    selectionMode: "latest",
    setSelectedChip: vi.fn(),
    setSelectionMode: vi.fn(),
  }),
  useRangeModeUrlState: () => ({
    startDate: "2026-06-01T00:00",
    endDate: "2026-06-08T00:00",
    setStartDate: vi.fn(),
    setEndDate: vi.fn(),
    setQuickRange: vi.fn(),
    hasUrlRange: true,
  }),
}));
vi.mock("@/components/selectors/ChipSelector", () => ({ ChipSelector: () => null }));
vi.mock("@/components/selectors/CooldownSelector", () => ({ CooldownSelector: () => null }));
vi.mock("@/components/ui/TimeRangeSelector", () => ({ TimeRangeSelector: () => null }));
vi.mock("@/components/ui/Skeleton/PageSkeletons", () => ({
  MetricsPageSkeleton: () => <div>Skeleton</div>,
}));
vi.mock("../OverviewCdfChart", () => ({ OverviewCdfChart: () => null }));
vi.mock("../OverviewSummaryTable", () => ({ OverviewSummaryTable: () => null }));
vi.mock("../OverviewChipNoteCard", () => ({ OverviewChipNoteCard: () => null }));
vi.mock("../OverviewTargetNoteModal", () => ({ OverviewTargetNoteModal: () => null }));
vi.mock("../OverviewMetricModal", () => ({ OverviewMetricModal: () => null }));
vi.mock("../CouplingMetricGrid", () => ({ CouplingMetricGrid: () => null }));
vi.mock("../QubitMetricGrid", () => ({
  QubitMetricGrid: ({
    metricData,
  }: {
    metricData: Record<string, { value: number | null }> | null;
  }) =>
    metricData ? (
      <div data-testid="qubit-grid">
        {Object.values(metricData)
          .map((item) => String(item.value))
          .join(",")}
      </div>
    ) : null,
}));

const CONFIG = {
  qubit_metrics: {
    t1: { title: "T1", unit: "us", scale: 1, evaluation: { mode: "maximize" } },
  },
  coupling_metrics: {},
  color_scale: { colors: [] },
};

type Reply = "error" | Promise<"error" | unknown> | unknown;
let configReply: () => Reply;
let metricsReply: (url: string) => Reply;
const metricsUrls: string[] = [];
const originalAdapter = AXIOS_INSTANCE.defaults.adapter;

const metrics = (value: number) => ({
  chip_id: urlState.chip,
  qubit_metrics: { t1: { Q00: { value } } },
  coupling_metrics: {},
});

const fakeAdapter: AxiosAdapter = async (config: InternalAxiosRequestConfig) => {
  const url = String(config.url);
  if (url !== "/metrics/config") metricsUrls.push(url);
  let answer = url === "/metrics/config" ? configReply() : metricsReply(url);
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
  const view = render(
    <QueryClientProvider client={client}>
      <OverviewPageContent />
    </QueryClientProvider>,
  );
  const rerender = () =>
    view.rerender(
      <QueryClientProvider client={client}>
        <OverviewPageContent />
      </QueryClientProvider>,
    );
  return { client, rerender };
}

/** A reply held until the test releases it. */
function held<T>() {
  let release: (value: T) => void = () => undefined;
  const promise = new Promise<T>((resolve) => (release = resolve));
  return { promise, release: (value: T) => release(value) };
}

const refetchMetrics = (client: QueryClient) =>
  act(async () => {
    await client.refetchQueries({ predicate: (query) => query.queryKey[0] !== "/metrics/config" });
  });

beforeEach(() => {
  AXIOS_INSTANCE.defaults.adapter = fakeAdapter;
  urlState.chip = "chip-1";
  configReply = () => CONFIG;
  metricsReply = () => metrics(10);
  metricsUrls.length = 0;
});

afterEach(() => {
  cleanup();
  AXIOS_INSTANCE.defaults.adapter = originalAdapter;
  localStorage.clear();
});

describe("OverviewPageContent failures", () => {
  it("retries a failed metrics configuration in place", async () => {
    configReply = () => "error";
    setup();
    expect(await screen.findByText("Could not load the metrics configuration")).toBeInTheDocument();

    const reply = held<unknown>();
    configReply = () => reply.promise;
    fireEvent.click(screen.getByRole("button", { name: "Try Again" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Try Again" })).toBeDisabled());
    expect(screen.queryByText("Skeleton")).not.toBeInTheDocument();

    await act(async () => reply.release(CONFIG));
    expect(await screen.findByTestId("qubit-grid")).toHaveTextContent("10");
    expect(screen.queryByText("Could not load the metrics configuration")).not.toBeInTheDocument();
  });

  it("retries a failed first metrics load in place", async () => {
    metricsReply = () => "error";
    setup();
    expect(await screen.findByText("Could not load overview data")).toBeInTheDocument();

    const reply = held<unknown>();
    metricsReply = () => reply.promise;
    fireEvent.click(screen.getByRole("button", { name: "Try Again" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Try Again" })).toBeDisabled());
    expect(screen.getByText("Could not load overview data")).toBeInTheDocument();

    await act(async () => reply.release(metrics(12)));
    expect(await screen.findByTestId("qubit-grid")).toHaveTextContent("12");
  });

  it("keeps the loaded values when a background refetch fails", async () => {
    const { client } = setup();
    expect(await screen.findByTestId("qubit-grid")).toHaveTextContent("10");

    metricsReply = () => "error";
    await refetchMetrics(client);
    expect(await screen.findByText(/Could not refresh overview data/)).toBeInTheDocument();
    expect(screen.getByTestId("qubit-grid")).toHaveTextContent("10");

    const reply = held<unknown>();
    metricsReply = () => reply.promise;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Retry" })).toBeDisabled());
    await act(async () => reply.release(metrics(14)));
    await waitFor(() => expect(screen.getByTestId("qubit-grid")).toHaveTextContent("14"));
    expect(screen.queryByText(/Could not refresh overview data/)).not.toBeInTheDocument();
  });

  it("does not show another chip's values after the chip changes", async () => {
    const { client, rerender } = setup();
    expect(await screen.findByTestId("qubit-grid")).toHaveTextContent("10");
    metricsReply = () => "error";
    await refetchMetrics(client);
    expect(await screen.findByText(/Could not refresh overview data/)).toBeInTheDocument();

    // The other chip fails on its first load: its error shows, not chip-1's values or warning.
    urlState.chip = "chip-2";
    rerender();
    expect(await screen.findByText("Could not load overview data")).toBeInTheDocument();
    expect(screen.queryByTestId("qubit-grid")).not.toBeInTheDocument();
    expect(screen.queryByText(/Could not refresh overview data/)).not.toBeInTheDocument();
    expect(metricsUrls[metricsUrls.length - 1]).toContain("chip-2");
  });
});
