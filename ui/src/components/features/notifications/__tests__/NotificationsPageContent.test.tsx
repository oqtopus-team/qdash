import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AxiosError, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { NuqsTestingAdapter, type UrlUpdateEvent } from "nuqs/adapters/testing";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AXIOS_INSTANCE } from "@/lib/api/custom-instance";
import type { NotificationResponse } from "@/schemas";

import { NotificationsPageContent } from "../NotificationsPageContent";

// The generated hooks and a real QueryClient decide what is shown; only the network is faked.
function notification(id: string, read: boolean): NotificationResponse {
  return {
    id,
    project_id: "project-a",
    recipient_username: "alice",
    actor_username: "bob",
    kind: "mention",
    source_type: "forum",
    source_id: id,
    target_url: `/forum/${id}`,
    title: `Notification ${id}`,
    read_at: read ? "2026-11-01T00:00:00Z" : null,
    created_at: "2026-11-01T00:00:00Z",
  };
}

let inbox: NotificationResponse[] = [];
let failList = false;
const listRequests: Record<string, unknown>[] = [];
const markAllCalls: string[] = [];
const originalAdapter = AXIOS_INSTANCE.defaults.adapter;

const fakeAdapter: AxiosAdapter = async (config: InternalAxiosRequestConfig) => {
  const ok = (data: unknown) => ({ data, status: 200, statusText: "OK", headers: {}, config });
  if (config.url === "/notifications/read-all") {
    markAllCalls.push(String(config.method));
    inbox = inbox.map((item) => ({ ...item, read_at: "2026-11-02T00:00:00Z" }));
    return ok({ updated: inbox.length });
  }
  if (config.url === "/notifications/unread-count") {
    return ok({ unread_count: inbox.filter((item) => item.read_at == null).length });
  }
  const params = { ...(config.params as Record<string, unknown>) };
  listRequests.push(params);
  if (failList) {
    throw new AxiosError("Request failed", "ERR_BAD_RESPONSE", config, null, {
      data: { detail: "boom" },
      status: 500,
      statusText: "Internal Server Error",
      headers: {},
      config,
    });
  }
  const unread = inbox.filter((item) => item.read_at == null);
  const shown = params.unread_only ? unread : inbox;
  return ok({
    notifications: shown,
    total: shown.length,
    unread_count: unread.length,
    skip: 0,
    limit: 100,
  });
};

function setup(searchParams = "") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onUrlUpdate = vi.fn<(event: UrlUpdateEvent) => void>();
  render(
    <QueryClientProvider client={client}>
      <NuqsTestingAdapter searchParams={searchParams} onUrlUpdate={onUrlUpdate} hasMemory>
        <NotificationsPageContent />
      </NuqsTestingAdapter>
    </QueryClientProvider>,
  );
  return { client, onUrlUpdate };
}

const lastRequest = () => listRequests[listRequests.length - 1];

beforeEach(() => {
  AXIOS_INSTANCE.defaults.adapter = fakeAdapter;
  inbox = [notification("1", false), notification("2", true)];
  failList = false;
  listRequests.length = 0;
  markAllCalls.length = 0;
});

afterEach(() => {
  cleanup();
  AXIOS_INSTANCE.defaults.adapter = originalAdapter;
});

describe("NotificationsPageContent filter", () => {
  it("shows every item by default and only unread items when filtered, in the URL", async () => {
    const { onUrlUpdate } = setup();
    expect(await screen.findByText("Notification 2")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "All" })).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(screen.getByRole("button", { name: "Unread only" }));
    // The unread list is its own query, so wait for its answer rather than the loading gap.
    await waitFor(() => expect(lastRequest()).toMatchObject({ unread_only: true }));
    expect(await screen.findByText("Notification 1")).toBeInTheDocument();
    expect(screen.queryByText("Notification 2")).not.toBeInTheDocument();
    await waitFor(() =>
      expect(onUrlUpdate.mock.calls[onUrlUpdate.mock.calls.length - 1]?.[0].queryString).toBe(
        "?filter=unread",
      ),
    );
  });

  it("restores the unread filter from the URL and ignores unknown values", async () => {
    setup("filter=unread");
    await screen.findByText("Notification 1");
    expect(lastRequest()).toMatchObject({ unread_only: true });
    cleanup();

    setup("filter=bogus");
    await screen.findByText("Notification 2");
    expect(lastRequest()).toMatchObject({ unread_only: false });
  });

  it("marks everything read and then shows the unread empty state with a way back", async () => {
    setup("filter=unread");
    await screen.findByText("Notification 1");

    fireEvent.click(screen.getByRole("button", { name: "Mark all read" }));
    expect(await screen.findByText("You have read everything in your inbox.")).toBeInTheDocument();
    expect(markAllCalls).toEqual(["patch"]);
    expect(screen.getByRole("button", { name: "Mark all read" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Show all items" }));
    expect(await screen.findByText("Notification 1")).toBeInTheDocument();
    expect(screen.getByText("Notification 2")).toBeInTheDocument();
  });

  it("says the inbox is empty when there is nothing at all", async () => {
    inbox = [];
    setup();
    expect(await screen.findByText("Inbox is empty")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Show all items" })).not.toBeInTheDocument();
  });
});

describe("NotificationsPageContent failures", () => {
  it("retries a failed first load in place", async () => {
    failList = true;
    setup();
    fireEvent.click(await screen.findByRole("button", { name: "Try Again" }));
    await waitFor(() => expect(listRequests.length).toBe(2));

    failList = false;
    fireEvent.click(await screen.findByRole("button", { name: "Try Again" }));
    expect(await screen.findByText("Notification 1")).toBeInTheDocument();
    expect(screen.queryByText("Could not load the inbox")).not.toBeInTheDocument();
  });

  it("keeps loaded items when a background refetch fails", async () => {
    const { client } = setup();
    await screen.findByText("Notification 1");

    failList = true;
    await act(async () => {
      await client.refetchQueries();
    });
    expect(await screen.findByText(/Could not refresh the inbox/)).toBeInTheDocument();
    expect(screen.getByText("Notification 1")).toBeInTheDocument();

    failList = false;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() =>
      expect(screen.queryByText(/Could not refresh the inbox/)).not.toBeInTheDocument(),
    );
  });
});
