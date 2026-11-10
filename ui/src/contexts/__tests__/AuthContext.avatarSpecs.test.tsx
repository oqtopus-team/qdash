import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AuthProvider, useAuth } from "@/contexts/AuthContext";
import { useCustomAvatarSpec } from "@/lib/avatar/avatarSpecs";

const mocks = vi.hoisted(() => ({
  listUserAvatars: vi.fn(),
  login: vi.fn(),
}));

vi.mock("@/client/user-avatar/user-avatar", () => ({ listUserAvatars: mocks.listUserAvatars }));

vi.mock("@/client/auth/auth", () => ({
  useGetCurrentUser: () => ({ data: undefined, error: null }),
  useLogin: () => ({ mutateAsync: mocks.login, reset: vi.fn() }),
  useLogout: () => ({ mutateAsync: vi.fn(), reset: vi.fn() }),
}));

const ALICE_SESSION_SPEC = "v1:k3x9q2a-1.-2:p0w7zz:stripes:c";
const BOB_SESSION_SPEC = "v1:abc:def:solid:c";

type AvatarList = { data: { avatars: { username: string; spec: string }[] } };

function deferred() {
  let resolve!: (value: AvatarList) => void;
  const promise = new Promise<AvatarList>((res) => {
    resolve = res;
  });
  return { promise, resolve };
}

function specs(spec: string): AvatarList {
  return { data: { avatars: [{ username: "carol", spec }] } };
}

let auth: ReturnType<typeof useAuth> | null = null;

function Probe() {
  auth = useAuth();
  return <span data-testid="carol">{useCustomAvatarSpec("carol") ?? "automatic"}</span>;
}

function shown(): string | null {
  return screen.getByTestId("carol").textContent;
}

function clearCookie() {
  document.cookie = "access_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
}

describe("AuthProvider avatar spec session", () => {
  beforeEach(() => {
    mocks.listUserAvatars.mockReset();
    mocks.login.mockReset();
    clearCookie();
  });

  afterEach(() => {
    cleanup();
    clearCookie();
    auth = null;
  });

  it("makes no lookup while signed out and fetches after login", async () => {
    mocks.listUserAvatars.mockResolvedValue(specs(ALICE_SESSION_SPEC));
    mocks.login.mockResolvedValue({ data: { access_token: "alice-token", username: "alice" } });
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await act(async () => {});
    expect(mocks.listUserAvatars).not.toHaveBeenCalled();
    expect(shown()).toBe("automatic");

    await act(() => auth!.login("alice", "password"));
    await waitFor(() => expect(shown()).toBe(ALICE_SESSION_SPEC));
    expect(mocks.listUserAvatars).toHaveBeenCalledTimes(1);
  });

  it("rejects a lookup of the previous account after another login", async () => {
    document.cookie = "access_token=alice-token; path=/";
    const aliceLookup = deferred();
    const bobLookup = deferred();
    mocks.listUserAvatars
      .mockReturnValueOnce(aliceLookup.promise)
      .mockReturnValueOnce(bobLookup.promise);
    mocks.login.mockResolvedValue({ data: { access_token: "bob-token", username: "bob" } });

    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(mocks.listUserAvatars).toHaveBeenCalledTimes(1));

    // Bob signs in while Alice's lookup is still pending.
    await act(() => auth!.login("bob", "password"));
    await waitFor(() => expect(mocks.listUserAvatars).toHaveBeenCalledTimes(2));

    await act(async () => aliceLookup.resolve(specs(ALICE_SESSION_SPEC)));
    expect(shown()).toBe("automatic");

    await act(async () => bobLookup.resolve(specs(BOB_SESSION_SPEC)));
    expect(shown()).toBe(BOB_SESSION_SPEC);
  });
});
