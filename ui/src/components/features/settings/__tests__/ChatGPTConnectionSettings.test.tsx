import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatGPTConnectionSettings } from "../ChatGPTConnectionSettings";

type Callbacks = { onSuccess?: (response: { data: unknown }) => void };

const mocks = vi.hoisted(() => ({
  connection: null as Record<string, unknown> | null,
  mutations: {} as Record<string, { mutate: ReturnType<typeof vi.fn>; callbacks: Callbacks }>,
  setQueryData: vi.fn(),
  invalidateQueries: vi.fn(),
}));

function mutation(name: string) {
  return (options?: { mutation?: Callbacks }) => {
    const entry = (mocks.mutations[name] ??= { mutate: vi.fn(), callbacks: {} });
    entry.callbacks = options?.mutation ?? {};
    return { mutate: entry.mutate, isPending: false };
  };
}

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({
    setQueryData: mocks.setQueryData,
    invalidateQueries: mocks.invalidateQueries,
  }),
}));
vi.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ success: vi.fn(), error: vi.fn(), warning: vi.fn() }),
}));
vi.mock("@/client/copilot/copilot", () => ({
  getGetChatGPTConnectionQueryKey: () => ["chatgpt-connection"],
  useGetChatGPTConnection: () => ({
    data: mocks.connection ? { data: mocks.connection } : undefined,
    isLoading: false,
    isError: false,
  }),
  useStartChatGPTAuthorization: mutation("start"),
  useCompleteChatGPTAuthorization: mutation("complete"),
  useDisconnectChatGPT: mutation("disconnect"),
  useRefreshChatGPTModels: mutation("refresh"),
  useAcknowledgeChatGPTWelcome: mutation("welcome"),
}));

const REDIRECT = "http://127.0.0.1:1455/auth/callback";

function connection(overrides: Record<string, unknown> = {}) {
  return {
    available: true,
    status: "not_connected",
    can_reconnect: false,
    plan_usage_enabled: false,
    welcome_pending: false,
    email: null,
    connected_at: null,
    last_error: null,
    models: [],
    usage_url: "https://chatgpt.com/settings/usage",
    ...overrides,
  };
}

beforeEach(() => {
  mocks.connection = connection();
  mocks.mutations = {};
  localStorage.clear();
  sessionStorage.clear();
});
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ChatGPTConnectionSettings", () => {
  it("signs in through the pasted loopback address without keeping it", () => {
    render(<ChatGPTConnectionSettings />);
    fireEvent.click(screen.getByRole("button", { name: "Continue with ChatGPT" }));
    expect(mocks.mutations.start.mutate).toHaveBeenCalledWith({
      data: { new_account: false, enable_plan: false },
    });

    act(() =>
      mocks.mutations.start.callbacks.onSuccess?.({
        data: {
          authorization_url: "https://auth.openai.com/api/accounts/authorize?state=s",
          redirect_uri: REDIRECT,
          expires_at: "2026-11-17T00:10:00Z",
        },
      }),
    );
    const link = screen.getByRole("link", { name: /Open the ChatGPT sign-in page/ });
    expect(link.getAttribute("href")).toContain("https://auth.openai.com/");
    expect(link.getAttribute("rel")).toContain("noopener");

    const input = screen.getByLabelText("Address from the browser");
    const finish = screen.getByRole("button", { name: "Finish connecting" }) as HTMLButtonElement;
    fireEvent.change(input, { target: { value: "http://localhost:1455/auth/callback?code=c" } });
    expect(finish.disabled).toBe(true);
    expect(screen.getByText(`The address must start with ${REDIRECT}`)).toBeTruthy();

    const callback = `${REDIRECT}?code=c&state=s&client_id=oaiapp_x`;
    fireEvent.change(input, { target: { value: callback } });
    fireEvent.click(finish);
    expect(mocks.mutations.complete.mutate).toHaveBeenCalledWith({
      data: { callback_url: callback },
    });
    expect(JSON.stringify({ ...localStorage, ...sessionStorage })).not.toContain("code=c");

    act(() =>
      mocks.mutations.complete.callbacks.onSuccess?.({ data: connection({ status: "connected" }) }),
    );
    expect(screen.queryByLabelText("Address from the browser")).toBeNull();
    expect(mocks.setQueryData).toHaveBeenCalled();
  });

  it("shows the connected account, its models and a confirmed disconnect", () => {
    mocks.connection = connection({
      status: "connected",
      plan_usage_enabled: true,
      can_reconnect: true,
      email: "alice@example.com",
      models: [
        { slug: "gpt-6.1-sol", display_name: "GPT-6.1 Sol", supported: true },
        { slug: "old", display_name: "Old", supported: false },
      ],
    });
    render(<ChatGPTConnectionSettings />);
    expect(screen.getByText("Connected as alice@example.com")).toBeTruthy();
    expect(screen.getByText(/GPT-6.1 Sol/)).toBeTruthy();
    expect(screen.queryByText(/Old/)).toBeNull();
    expect(screen.getByRole("link", { name: /Manage usage/ }).getAttribute("href")).toBe(
      "https://chatgpt.com/settings/usage",
    );

    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    expect(mocks.mutations.disconnect.mutate).not.toHaveBeenCalled();
    const disconnectButtons = screen.getAllByRole("button", { name: "Disconnect" });
    fireEvent.click(disconnectButtons[disconnectButtons.length - 1]);
    expect(mocks.mutations.disconnect.mutate).toHaveBeenCalled();
  });

  it("offers reconnecting or another account after signing out", () => {
    mocks.connection = connection({ status: "signed_out", can_reconnect: true });
    render(<ChatGPTConnectionSettings />);
    fireEvent.click(screen.getByRole("button", { name: "Use a different account" }));
    expect(mocks.mutations.start.mutate).toHaveBeenCalledWith({
      data: { new_account: true, enable_plan: false },
    });
  });

  it("asks again for plan usage when it was not granted", () => {
    mocks.connection = connection({ status: "plan_disabled", can_reconnect: true });
    render(<ChatGPTConnectionSettings />);
    expect(screen.getByText(/plan usage is not enabled/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Enable ChatGPT plan usage" }));
    expect(mocks.mutations.start.mutate).toHaveBeenCalledWith({
      data: { new_account: false, enable_plan: true },
    });
  });

  it("explains a usage limit with Manage usage as the action", () => {
    mocks.connection = connection({
      status: "connected",
      last_error: {
        code: "subscription_sharing_usage_limit_exceeded",
        message: "limit",
      },
    });
    render(<ChatGPTConnectionSettings />);
    expect(screen.getByText("Usage limit reached")).toBeTruthy();
    expect(screen.getAllByRole("link", { name: /Manage usage/ }).length).toBeGreaterThan(0);
  });

  it("confirms plan usage once after the first sign-in", () => {
    mocks.connection = connection({ status: "connected", welcome_pending: true });
    render(<ChatGPTConnectionSettings />);
    expect(screen.getByText("You're using your ChatGPT plan")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Got it" }));
    expect(mocks.mutations.welcome.mutate).toHaveBeenCalled();
  });

  it("says when the server cannot store connections", () => {
    mocks.connection = connection({ available: false });
    render(<ChatGPTConnectionSettings />);
    expect(screen.getByText(/not set up on this QDash server/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Continue with ChatGPT" })).toBeNull();
  });
});
