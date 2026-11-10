import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  currentAvatarSpecSession,
  requestAvatarSpec,
  setAvatarSpec,
  startAvatarSpecSession,
  useCustomAvatarSpec,
} from "@/lib/avatar/avatarSpecs";

const listUserAvatars = vi.hoisted(() => vi.fn());

vi.mock("@/client/user-avatar/user-avatar", () => ({ listUserAvatars }));

const OLD_SPEC = "v1:k3x9q2a-1.-2:p0w7zz:stripes:c";
const NEW_SPEC = "v1:abc:def:solid:c";

type AvatarList = { data: { avatars: { username: string; spec: string }[] } };

function deferred() {
  let resolve!: (value: AvatarList) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<AvatarList>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

function specs(avatars: { username: string; spec: string }[]): AvatarList {
  return { data: { avatars } };
}

function Spec({ username }: { username: string }) {
  return <span data-testid={username}>{useCustomAvatarSpec(username) ?? "automatic"}</span>;
}

function shown(username: string): string | null {
  return screen.getByTestId(username).textContent;
}

describe("avatar spec cache sessions", () => {
  beforeEach(() => {
    listUserAvatars.mockReset();
    listUserAvatars.mockResolvedValue(specs([]));
    startAvatarSpecSession(true);
  });

  afterEach(() => {
    cleanup();
  });

  it("makes no lookup without an authenticated session", async () => {
    act(() => startAvatarSpecSession(false));
    render(<Spec username="alice" />);
    await act(async () => {});
    expect(listUserAvatars).not.toHaveBeenCalled();
    expect(shown("alice")).toBe("automatic");
  });

  it("drops cached specs at once when the session changes and fetches them again", async () => {
    listUserAvatars.mockResolvedValueOnce(specs([{ username: "alice", spec: OLD_SPEC }]));
    render(<Spec username="alice" />);
    await waitFor(() => expect(shown("alice")).toBe(OLD_SPEC));

    const next = deferred();
    listUserAvatars.mockReturnValueOnce(next.promise);
    act(() => startAvatarSpecSession(true));
    // The automatic avatar shows synchronously until the new session's lookup returns.
    expect(shown("alice")).toBe("automatic");
    await waitFor(() => expect(listUserAvatars).toHaveBeenCalledTimes(2));

    await act(async () => next.resolve(specs([{ username: "alice", spec: NEW_SPEC }])));
    expect(shown("alice")).toBe(NEW_SPEC);
  });

  it("ignores a lookup response that arrives after logout and login", async () => {
    const stale = deferred();
    listUserAvatars.mockReturnValueOnce(stale.promise);
    render(<Spec username="alice" />);
    await waitFor(() => expect(listUserAvatars).toHaveBeenCalledTimes(1));

    act(() => startAvatarSpecSession(false));
    const fresh = deferred();
    listUserAvatars.mockReturnValueOnce(fresh.promise);
    act(() => startAvatarSpecSession(true));
    await waitFor(() => expect(listUserAvatars).toHaveBeenCalledTimes(2));

    await act(async () => stale.resolve(specs([{ username: "alice", spec: OLD_SPEC }])));
    expect(shown("alice")).toBe("automatic");

    await act(async () => fresh.resolve(specs([{ username: "alice", spec: NEW_SPEC }])));
    expect(shown("alice")).toBe(NEW_SPEC);
  });

  it("does not let a finished prior-session request clear the new session's pending lookup", async () => {
    const stale = deferred();
    listUserAvatars.mockReturnValueOnce(stale.promise);
    render(<Spec username="alice" />);
    await waitFor(() => expect(listUserAvatars).toHaveBeenCalledTimes(1));

    const fresh = deferred();
    listUserAvatars.mockReturnValueOnce(fresh.promise);
    act(() => startAvatarSpecSession(true));
    await waitFor(() => expect(listUserAvatars).toHaveBeenCalledTimes(2));

    // A failed prior-session request neither marks the user failed nor frees a duplicate lookup.
    await act(async () => stale.reject(new Error("Network Error")));
    requestAvatarSpec("alice");
    await act(async () => {});
    expect(listUserAvatars).toHaveBeenCalledTimes(2);

    await act(async () => fresh.resolve(specs([{ username: "alice", spec: NEW_SPEC }])));
    expect(shown("alice")).toBe(NEW_SPEC);
  });

  it("drops lookups queued but not yet sent when the session changes", async () => {
    vi.useFakeTimers();
    try {
      requestAvatarSpec("alice");
      startAvatarSpecSession(false);
      await vi.runAllTimersAsync();
      expect(listUserAvatars).not.toHaveBeenCalled();
    } finally {
      vi.useRealTimers();
    }
  });

  it("drops a saved spec whose save started in a previous session", async () => {
    render(<Spec username="alice" />);
    await act(async () => {});
    const savedIn = currentAvatarSpecSession();

    act(() => startAvatarSpecSession(true));
    act(() => setAvatarSpec("alice", OLD_SPEC, savedIn));
    expect(shown("alice")).toBe("automatic");

    act(() => setAvatarSpec("alice", NEW_SPEC, currentAvatarSpecSession()));
    expect(shown("alice")).toBe(NEW_SPEC);
  });

  it("keeps a spec saved during a lookup over the lookup's older response", async () => {
    const pending = deferred();
    listUserAvatars.mockReturnValueOnce(pending.promise);
    render(<Spec username="alice" />);
    await waitFor(() => expect(listUserAvatars).toHaveBeenCalledTimes(1));

    act(() => setAvatarSpec("alice", NEW_SPEC));
    await act(async () => pending.resolve(specs([{ username: "alice", spec: OLD_SPEC }])));
    expect(shown("alice")).toBe(NEW_SPEC);
  });

  it("splits more than 100 usernames into batches of 100", async () => {
    const usernames = Array.from({ length: 150 }, (_, index) => `user${index}`);
    render(
      <>
        {usernames.map((username) => (
          <Spec key={username} username={username} />
        ))}
      </>,
    );
    await waitFor(() => expect(listUserAvatars).toHaveBeenCalledTimes(2));
    expect(listUserAvatars.mock.calls[0][0].username).toHaveLength(100);
    expect(listUserAvatars.mock.calls[1][0].username).toHaveLength(50);
  });
});
