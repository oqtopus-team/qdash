import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AxiosError, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { NuqsTestingAdapter } from "nuqs/adapters/testing";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AXIOS_INSTANCE } from "@/lib/api/custom-instance";

import { MetricsPageContent } from "../MetricsPageContent";

// The metrics config and chip metrics come from the generated hooks over a faked network, with a
// real QueryClient, so loading, error and refetch states follow TanStack Query. Charts, grids and
// selectors are reduced to what the assertions read.
vi.mock("@/client/chip/chip", () => ({
  useListChips: () => ({ data: { data: { chips: [{ chip_id: "64Qv1" }] } }, isLoading: false }),
  useGetChip: () => ({ data: { data: { chip_id: "64Qv1", size: 4 } } }),
}));
vi.mock("@/components/selectors/ChipSelector", () => ({ ChipSelector: () => null }));
vi.mock("@/components/selectors/CooldownSelector", () => ({ CooldownSelector: () => null }));
vi.mock("../MetricsCdfChart", () => ({ MetricsCdfChart: () => null }));
vi.mock("../MetricsPdfDownloadButton", () => ({ MetricsPdfDownloadButton: () => null }));
vi.mock("../MetricsYamlDownloadButton", () => ({ MetricsYamlDownloadButton: () => null }));
vi.mock("../CouplingMetricsGrid", () => ({ CouplingMetricsGrid: () => null }));
vi.mock("../QubitMetricsGrid", () => ({
  QubitMetricsGrid: ({ metricData }: { metricData: Record<string, { value: number | null }> }) => (
    <div data-testid="qubit-grid">
      {Object.entries(metricData ?? {})
        .map(([qid, item]) => `Q${qid}=${item.value}`)
        .join(",")}
    </div>
  ),
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
let metricsReply: () => Reply;
const originalAdapter = AXIOS_INSTANCE.defaults.adapter;

const metrics = (value: number) => ({
  chip_id: "64Qv1",
  qubit_metrics: { t1: { Q00: { value } } },
  coupling_metrics: {},
});

const fakeAdapter: AxiosAdapter = async (config: InternalAxiosRequestConfig) => {
  let answer = config.url === "/metrics/config" ? configReply() : metricsReply();
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
  render(
    <QueryClientProvider client={client}>
      <NuqsTestingAdapter searchParams="chip=64Qv1" hasMemory>
        <MetricsPageContent />
      </NuqsTestingAdapter>
    </QueryClientProvider>,
  );
  return client;
}

/** A reply held until the test releases it. */
function held<T>() {
  let release: (value: T) => void = () => undefined;
  const promise = new Promise<T>((resolve) => (release = resolve));
  return { promise, release: (value: T) => release(value) };
}

beforeEach(() => {
  AXIOS_INSTANCE.defaults.adapter = fakeAdapter;
  configReply = () => CONFIG;
  metricsReply = () => metrics(10);
});

afterEach(() => {
  cleanup();
  AXIOS_INSTANCE.defaults.adapter = originalAdapter;
  localStorage.clear();
});

describe("MetricsPageContent failures", () => {
  it("retries a failed metrics configuration in place", async () => {
    configReply = () => "error";
    setup();
    expect(await screen.findByText("Could not load the metrics configuration")).toBeInTheDocument();

    const reply = held<unknown>();
    configReply = () => reply.promise;
    fireEvent.click(screen.getByRole("button", { name: "Try Again" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Try Again" })).toBeDisabled());

    await act(async () => reply.release(CONFIG));
    expect(await screen.findByTestId("qubit-grid")).toHaveTextContent("Q0=10");
    expect(screen.queryByText("Could not load the metrics configuration")).not.toBeInTheDocument();
  });

  it("retries a failed first metrics load in place", async () => {
    metricsReply = () => "error";
    setup();
    expect(await screen.findByText("Could not load metrics data")).toBeInTheDocument();

    metricsReply = () => metrics(12);
    fireEvent.click(screen.getByRole("button", { name: "Try Again" }));
    expect(await screen.findByTestId("qubit-grid")).toHaveTextContent("Q0=12");
  });

  it("keeps the loaded values when a background refetch fails", async () => {
    const client = setup();
    expect(await screen.findByTestId("qubit-grid")).toHaveTextContent("Q0=10");

    metricsReply = () => "error";
    await act(async () => {
      await client.refetchQueries({
        predicate: (query) => query.queryKey[0] !== "/metrics/config",
      });
    });
    expect(await screen.findByText(/Could not refresh metrics data/)).toBeInTheDocument();
    expect(screen.getByTestId("qubit-grid")).toHaveTextContent("Q0=10");

    const reply = held<unknown>();
    metricsReply = () => reply.promise;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Retry" })).toBeDisabled());
    await act(async () => reply.release(metrics(14)));
    await waitFor(() => expect(screen.getByTestId("qubit-grid")).toHaveTextContent("Q0=14"));
    expect(screen.queryByText(/Could not refresh metrics data/)).not.toBeInTheDocument();
  });
});
