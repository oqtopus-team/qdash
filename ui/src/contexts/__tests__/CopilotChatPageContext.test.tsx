import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";

import {
  CopilotChatSessionProvider,
  useCopilotChatSessionContext,
} from "../CopilotChatSessionContext";

vi.mock("next/navigation", () => ({ usePathname: () => "/custom-dashboards/scripts/ms_1" }));

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
    if (url.endsWith("/copilot/chat/sessions") && !init?.method) {
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
  <CopilotChatSessionProvider>{children}</CopilotChatSessionProvider>
);

it("sends the open metric script editor's text with the page", async () => {
  const { result } = renderHook(() => useCopilotChatSessionContext(), { wrapper });
  await waitFor(() => expect(result.current.isLoadingSessions).toBe(false));

  act(() => {
    result.current.sendMessage("Add a count check", {
      page: {
        path: "/custom-dashboards/scripts/ms_1",
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
    path: "/custom-dashboards/scripts/ms_1",
    title: "Metric script: ZX90",
    metric_script: { script_id: "ms_1", name: "ZX90", code: "print(1)\n", dirty: true },
  });
});
