import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import { AgentChatSessionProvider, useAgentChatSessionContext } from "../AgentChatSessionContext";

vi.mock("next/navigation", () => ({ usePathname: () => "/dashboards/scripts/ms_1" }));

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (url.endsWith("/stream")) {
      return new Response(
        `event: result\ndata: ${JSON.stringify({ blocks: [], assessment: null })}\n\n`,
        {
          status: 200,
        },
      );
    }
    if (url.endsWith("/agent/chat/sessions") && !init?.method) {
      return Response.json({ sessions: [] });
    }
    const id = decodeURIComponent(String(url).split("/").pop() ?? "");
    return Response.json({ session_id: id, title: "", context: null, messages: [] });
  });
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

const wrapper = ({ children }: { children: ReactNode }) => (
  <AgentChatSessionProvider>{children}</AgentChatSessionProvider>
);

it("sends the open metric script editor's text with the page", async () => {
  const { result } = renderHook(() => useAgentChatSessionContext(), { wrapper });
  await waitFor(() => expect(result.current.isLoadingSessions).toBe(false));

  act(() => {
    result.current.sendMessage("Add a count check", {
      page: {
        path: "/dashboards/scripts/ms_1",
        title: "Metric script: ZX90",
        metricScript: { scriptId: "ms_1", name: "ZX90", code: "print(1)\n", dirty: true },
      },
    });
  });

  await waitFor(() =>
    expect(
      fetchMock.mock.calls.some(([url, init]) => String(url).endsWith("/stream") && init?.body),
    ).toBe(true),
  );
  const [, init] = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/stream"))!;
  const body = JSON.parse(String(init.body));
  expect(body.page).toEqual({
    path: "/dashboards/scripts/ms_1",
    title: "Metric script: ZX90",
    metric_script: { script_id: "ms_1", name: "ZX90", code: "print(1)\n", dirty: true },
  });
});

it("sends an editable dashboard's draft with the page in the API's shape", async () => {
  const { result } = renderHook(() => useAgentChatSessionContext(), { wrapper });
  await waitFor(() => expect(result.current.isLoadingSessions).toBe(false));

  act(() => {
    result.current.sendMessage("Add a ZX90 map", {
      page: {
        path: "/dashboards/dash-1",
        title: "Dashboard: Review",
        dashboard: {
          dashboardId: "dash-1",
          name: "Review",
          description: "",
          visibility: "private",
          chipId: "chip-1",
          version: 3,
          code: '{"panels":[]}',
          dirty: false,
        },
      },
    });
  });

  await waitFor(() =>
    expect(
      fetchMock.mock.calls.some(([url, init]) => String(url).endsWith("/stream") && init?.body),
    ).toBe(true),
  );
  const [, init] = fetchMock.mock.calls.find(([url]) => String(url).endsWith("/stream"))!;
  expect(JSON.parse(String(init.body)).page).toEqual({
    path: "/dashboards/dash-1",
    title: "Dashboard: Review",
    dashboard: {
      dashboard_id: "dash-1",
      name: "Review",
      description: null,
      visibility: "private",
      chip_id: "chip-1",
      version: 3,
      code: '{"panels":[]}',
      dirty: false,
    },
  });
});
