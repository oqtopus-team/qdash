import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AxiosError, type AxiosAdapter, type InternalAxiosRequestConfig } from "axios";
import { NuqsTestingAdapter, type UrlUpdateEvent } from "nuqs/adapters/testing";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AXIOS_INSTANCE } from "@/lib/api/custom-instance";
import type { NotificationResponse } from "@/schemas";

import { NotificationsPageContent } from "../NotificationsPageContent";

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("@/components/ui/Toast", () => ({ useToast: () => toast }));

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
let failMarkRead = false;
let failMarkAll = false;
/** When set, a mark read request waits for this promise to settle before answering. */
let markReadGate: Promise<void> | null = null;
const listRequests: Record<string, unknown>[] = [];
const markAllCalls: string[] = [];
const markReadCalls: string[] = [];
const originalAdapter = AXIOS_INSTANCE.defaults.adapter;

const fakeAdapter: AxiosAdapter = async (config: InternalAxiosRequestConfig) => {
  const ok = (data: unknown) => ({ data, status: 200, statusText: "OK", headers: {}, config });
  const fail = () =>
    new AxiosError("Request failed", "ERR_BAD_RESPONSE", config, null, {
      data: { detail: "boom" },
      status: 500,
      statusText: "Internal Server Error",
      headers: {},
      config,
    });
  const markRead = config.url?.match(/^\/notifications\/([^/]+)\/read$/);
  if (markRead) {
    markReadCalls.push(markRead[1]);
    if (markReadGate) await markReadGate.catch(() => undefined);
    if (failMarkRead) throw fail();
    inbox = inbox.map((item) =>
      item.id === markRead[1] ? { ...item, read_at: "2026-11-02T00:00:00Z" } : item,
    );
    return ok(inbox.find((item) => item.id === markRead[1]));
  }
  if (config.url === "/notifications/read-all") {
    markAllCalls.push(String(config.method));
    if (failMarkAll) throw fail();
    inbox = inbox.map((item) => ({ ...item, read_at: "2026-11-02T00:00:00Z" }));
    return ok({ updated: inbox.length });
  }
  if (config.url === "/notifications/unread-count") {
    return ok({ unread_count: inbox.filter((item) => item.read_at == null).length });
  }
  const params = { ...(config.params as Record<string, unknown>) };
  listRequests.push(params);
  if (failList) throw fail();
  const unread = inbox.filter((item) => item.read_at == null);
  const shown = params.unread_only ? unread : inbox;
  const skip = Number(params.skip ?? 0);
  const limit = Number(params.limit ?? 50);
  return ok({
    notifications: shown.slice(skip, skip + limit),
    total: shown.length,
    unread_count: unread.length,
    skip,
    limit,
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
const lastQuery = (onUrlUpdate: ReturnType<typeof setup>["onUrlUpdate"]) =>
  onUrlUpdate.mock.calls[onUrlUpdate.mock.calls.length - 1]?.[0];
/** `count` notifications, newest first, with ids `n1`..`n<count>`. */
const many = (count: number, read = false) =>
  Array.from({ length: count }, (_, index) => notification(`n${index + 1}`, read));

beforeEach(() => {
  AXIOS_INSTANCE.defaults.adapter = fakeAdapter;
  inbox = [notification("1", false), notification("2", true)];
  failList = false;
  failMarkRead = false;
  failMarkAll = false;
  markReadGate = null;
  listRequests.length = 0;
  markAllCalls.length = 0;
  markReadCalls.length = 0;
  toast.error.mockClear();
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

describe("NotificationsPageContent pagination", () => {
  it("pages through the inbox with skip and limit, keeping the page in the URL", async () => {
    inbox = many(60);
    const { onUrlUpdate } = setup();
    expect(await screen.findByText("Notification n50")).toBeInTheDocument();
    expect(screen.queryByText("Notification n51")).not.toBeInTheDocument();
    expect(lastRequest()).toMatchObject({ unread_only: false, skip: 0, limit: 50 });
    expect(screen.getByText("Page 1 of 2")).toBeInTheDocument();
    expect(screen.getByText("Items 1-50 of 60")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();

    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(await screen.findByText("Notification n51")).toBeInTheDocument();
    expect(lastRequest()).toMatchObject({ skip: 50, limit: 50 });
    expect(screen.queryByText("Notification n1")).not.toBeInTheDocument();
    expect(screen.getByText("Items 51-60 of 60")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
    await waitFor(() => expect(lastQuery(onUrlUpdate)?.queryString).toBe("?page=2"));
    expect(lastQuery(onUrlUpdate)?.options.history).toBe("push");
  });

  it("returns to the first page when the filter changes", async () => {
    inbox = many(60);
    const { onUrlUpdate } = setup("page=2");
    expect(await screen.findByText("Notification n51")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Unread only" }));
    await waitFor(() => expect(lastQuery(onUrlUpdate)?.queryString).toBe("?filter=unread"));
    expect(await screen.findByText("Notification n1")).toBeInTheDocument();
    expect(lastRequest()).toMatchObject({ unread_only: true, skip: 0 });
  });

  it("restores the filter and page from the URL", async () => {
    inbox = many(60);
    setup("filter=unread&page=2");
    expect(await screen.findByText("Notification n51")).toBeInTheDocument();
    expect(listRequests[0]).toMatchObject({ unread_only: true, skip: 50, limit: 50 });
    expect(screen.getByRole("button", { name: "Unread only" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("hides the page controls when everything fits on one page", async () => {
    setup();
    await screen.findByText("Notification 1");
    expect(screen.queryByRole("navigation", { name: "Inbox pages" })).not.toBeInTheDocument();
  });

  it("moves to the last page that has items when the shown page empties", async () => {
    inbox = many(55);
    const { onUrlUpdate } = setup("filter=unread&page=2");
    expect(await screen.findByText("Notification n55")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Mark all read" }));
    await waitFor(() => expect(lastQuery(onUrlUpdate)?.queryString).toBe("?filter=unread"));
    // The correction replaces the stale page rather than adding a history entry.
    expect(lastQuery(onUrlUpdate)?.options.history).toBe("replace");
    expect(await screen.findByText("You have read everything in your inbox.")).toBeInTheDocument();
    expect(lastRequest()).toMatchObject({ unread_only: true, skip: 0 });
  });

  it("corrects a page past the end of an old link", async () => {
    inbox = many(3);
    const { onUrlUpdate } = setup("page=9");
    expect(await screen.findByText("Notification n1")).toBeInTheDocument();
    await waitFor(() => expect(lastQuery(onUrlUpdate)?.queryString).toBe(""));
  });
});

describe("NotificationsPageContent mark read failures", () => {
  it("reports a failed mark all read and leaves the items unread for a retry", async () => {
    failMarkAll = true;
    setup();
    await screen.findByText("Notification 1");

    fireEvent.click(screen.getByRole("button", { name: "Mark all read" }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("boom"));
    expect(screen.getByText("1 unread item")).toBeInTheDocument();
    expect(screen.getByText("Unread")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Mark all read" })).toBeEnabled(),
    );

    failMarkAll = false;
    fireEvent.click(screen.getByRole("button", { name: "Mark all read" }));
    expect(await screen.findByText("No unread items")).toBeInTheDocument();
    expect(markAllCalls).toEqual(["patch", "patch"]);
    expect(toast.error).toHaveBeenCalledTimes(1);
  });

  it("reports a failed mark read when an unread item is opened", async () => {
    failMarkRead = true;
    setup();
    fireEvent.click(await screen.findByText("Notification 1"));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("boom"));
    expect(markReadCalls).toEqual(["1"]);
    expect(screen.getByText("1 unread item")).toBeInTheDocument();
  });

  it("still reports a failed mark read after opening the notification leaves the inbox", async () => {
    let rejectMarkRead: () => void = () => undefined;
    const pending = new Promise<void>((_, reject) => (rejectMarkRead = () => reject()));
    pending.catch(() => undefined);
    failMarkRead = true;
    markReadGate = pending;
    setup();
    fireEvent.click(await screen.findByText("Notification 1"));
    await waitFor(() => expect(markReadCalls).toEqual(["1"]));

    // Opening the link navigates away, which unmounts the inbox before the request settles.
    cleanup();
    rejectMarkRead();
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith("boom"));
  });

  it("does not mark an item that is already read", async () => {
    setup();
    fireEvent.click(await screen.findByText("Notification 2"));
    expect(markReadCalls).toEqual([]);
  });
});
