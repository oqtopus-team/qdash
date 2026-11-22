import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { AxiosAdapter, InternalAxiosRequestConfig } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AXIOS_INSTANCE } from "@/lib/api/custom-instance";

import { StopAgentSessionButton, stopOutcomeMessage } from "../StopAgentSessionButton";

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }));
vi.mock("sonner", () => ({ toast }));

const posts: {
  url: string;
  body: { idempotency_key: string; reason: string };
  project: unknown;
}[] = [];
const originalAdapter = AXIOS_INSTANCE.defaults.adapter;
const RESULT = {
  outcome: "stopped",
  session: { session_id: "ses-1", status: "cancelled" },
  in_flight: [{ kind: "measurement", id: "act-1", status: "queued", execution_id: "exec-1" }],
  closed_intervention_ids: [],
};

const fakeAdapter: AxiosAdapter = async (config: InternalAxiosRequestConfig) => {
  const body = typeof config.data === "string" ? JSON.parse(config.data) : config.data;
  posts.push({ url: config.url ?? "", body, project: config.headers?.["X-Project-Id"] });
  return { data: RESULT, status: 200, statusText: "OK", headers: {}, config };
};

function setup(onStopped = vi.fn()) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <StopAgentSessionButton sessionId="ses-1" projectId="lab-a" onStopped={onStopped} />
    </QueryClientProvider>,
  );
  return onStopped;
}

describe("StopAgentSessionButton", () => {
  beforeEach(() => {
    posts.length = 0;
    AXIOS_INSTANCE.defaults.adapter = fakeAdapter;
  });
  afterEach(() => {
    cleanup();
    AXIOS_INSTANCE.defaults.adapter = originalAdapter;
    vi.clearAllMocks();
  });

  it("stops the session in its project with a reason and says what still runs", async () => {
    const onStopped = setup();
    fireEvent.click(screen.getByRole("button", { name: "Stop session" }));
    expect(
      screen.getByText(/A measurement already sent to the hardware is not cancelled/),
    ).toBeTruthy();
    const confirm = screen
      .getAllByRole("button", { name: "Stop session" })
      .find(
        (button) =>
          button.className.includes("btn-error") && !button.className.includes("btn-outline"),
      );
    expect(confirm).toBeTruthy();
    // No reason, no stop.
    expect((confirm as HTMLButtonElement).disabled).toBe(true);
    fireEvent.change(screen.getByPlaceholderText(/for the audit/), {
      target: { value: "The user asked to stop" },
    });
    fireEvent.click(confirm as HTMLButtonElement);

    await waitFor(() => expect(onStopped).toHaveBeenCalled());
    expect(posts).toHaveLength(1);
    expect(posts[0]!.url).toBe("/agent-sessions/ses-1/stop");
    expect(posts[0]!.project).toBe("lab-a");
    expect(posts[0]!.body.reason).toBe("The user asked to stop");
    expect(posts[0]!.body.idempotency_key).toBeTruthy();
    expect(toast.success).toHaveBeenCalledWith(
      "Session stopped. Still running and not cancelled: measurement act-1 (queued)",
    );
  });

  it("reports a session that had already ended as unchanged", () => {
    expect(
      stopOutcomeMessage({
        outcome: "already_ended",
        session: { status: "expired" },
        in_flight: [],
      } as never),
    ).toBe("The session had already ended (expired)");
  });
});
