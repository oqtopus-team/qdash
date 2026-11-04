import type { ReactNode } from "react";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import type { AxiosAdapter, InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HomeExecutionActivity } from "@/components/features/home/HomeExecutionActivity";
import { AXIOS_INSTANCE } from "@/lib/api/custom-instance";

// The generated hook, the request interceptor, and a real QueryClient decide what is shown;
// only the network adapter is faked, and it answers with the project named in the header.
const mocks = vi.hoisted(() => ({ project: "project-a" as string | null }));
vi.mock("@/contexts/ProjectContext", () => ({ useProject: () => ({ projectId: mocks.project }) }));
vi.mock("@/contexts/ThemeContext", () => ({ useIsDarkTheme: () => false }));

const PROJECT_STORAGE_KEY = "qdash_current_project_id";
const COUNTS: Record<string, number> = { "project-a": 3, "project-b": 5 };

/** A 30-day window with `count` completed executions on its last day. */
function activity(count: number) {
  const end = Date.UTC(2026, 10, 2);
  const buckets = Array.from({ length: 30 }, (_, offset) => {
    const date = new Date(end - (29 - offset) * 86_400_000).toISOString().slice(0, 10);
    const completed = offset === 29 ? count : 0;
    const base = { completed, failed: 0, running: 0, scheduled: 0, cancelled: 0, other: 0 };
    return { date, ...base, total: completed };
  });
  return { chip_id: null, days: 30, timezone: "Asia/Tokyo", since: "", until: "", buckets };
}

/** Requests per project, each held until the test releases it. */
let pending: Array<{ project: string; release: () => void }> = [];
const originalAdapter = AXIOS_INSTANCE.defaults.adapter;

const fakeAdapter: AxiosAdapter = (config: InternalAxiosRequestConfig) => {
  const project = String(config.headers.get("X-Project-Id"));
  return new Promise((resolve) => {
    pending.push({
      project,
      release: () =>
        resolve({
          data: activity(COUNTS[project]),
          status: 200,
          statusText: "OK",
          headers: {},
          config,
        }),
    });
  });
};

async function release(project: string) {
  await waitFor(() => expect(pending.some((item) => item.project === project)).toBe(true));
  const held = pending.filter((item) => item.project === project);
  pending = pending.filter((item) => item.project !== project);
  await act(async () => held.forEach((item) => item.release()));
}

/** Switch projects the way ProjectContext does: storage, then invalidate, then rerender. */
async function switchTo(project: string, client: QueryClient, rerender: () => void) {
  localStorage.setItem(PROJECT_STORAGE_KEY, project);
  mocks.project = project;
  await act(async () => {
    void client.invalidateQueries();
    rerender();
  });
}

function setup() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  const view = render(<HomeExecutionActivity />, { wrapper });
  return { client, rerender: () => view.rerender(<HomeExecutionActivity />) };
}

const total = () => screen.queryByTestId("home-activity-total");
/** Completed executions on the last day cached under the project's key. */
const cachedTotal = (client: QueryClient, project: string) => {
  const data = client
    .getQueryCache()
    .findAll({ queryKey: ["/executions/activity"] })
    .find((query) => query.queryKey[query.queryKey.length - 1] === project)?.state.data as
    | { data: ReturnType<typeof activity> }
    | undefined;
  return data?.data.buckets[data.data.buckets.length - 1]?.completed;
};

beforeEach(() => {
  pending = [];
  mocks.project = "project-a";
  localStorage.setItem(PROJECT_STORAGE_KEY, "project-a");
  document.cookie = "access_token=token";
  AXIOS_INSTANCE.defaults.adapter = fakeAdapter;
});
afterEach(() => {
  cleanup();
  AXIOS_INSTANCE.defaults.adapter = originalAdapter;
  localStorage.removeItem(PROJECT_STORAGE_KEY);
  document.cookie = "access_token=; expires=Thu, 01 Jan 1970 00:00:00 GMT";
});

describe("HomeExecutionActivity across projects", () => {
  it("shows a placeholder, not the previous project's counts, while the new one loads", async () => {
    const { client, rerender } = setup();
    await release("project-a");
    await waitFor(() => expect(total()).toHaveTextContent("3executions"));

    await switchTo("project-b", client, rerender);

    expect(total()).toBeNull();
    expect(document.querySelector(".skeleton")).not.toBeNull();
    await release("project-b");
    await waitFor(() => expect(total()).toHaveTextContent("5executions"));
  });

  it("keeps the old project's refetch and late response under the old project", async () => {
    const { client, rerender } = setup();
    await release("project-a");
    await waitFor(() => expect(total()).toHaveTextContent("3executions"));

    // Invalidation refetches project-a's query before it unmounts, after storage moved to b.
    await switchTo("project-b", client, rerender);
    await release("project-a");

    expect(total()).toBeNull();
    expect(cachedTotal(client, "project-a")).toBe(3);
    await release("project-b");
    await waitFor(() => expect(total()).toHaveTextContent("5executions"));
    expect(cachedTotal(client, "project-b")).toBe(5);
  });

  it("returns to a project's own cached counts after switching back", async () => {
    const { client, rerender } = setup();
    await release("project-a");
    await switchTo("project-b", client, rerender);
    await release("project-a");
    await release("project-b");
    await waitFor(() => expect(total()).toHaveTextContent("5executions"));

    await switchTo("project-a", client, rerender);

    expect(total()).toHaveTextContent("3executions");
  });

  it("waits for a project before requesting anything", async () => {
    mocks.project = null;
    setup();

    expect(document.querySelector(".skeleton")).not.toBeNull();
    await act(async () => {});
    expect(pending).toHaveLength(0);
  });
});
