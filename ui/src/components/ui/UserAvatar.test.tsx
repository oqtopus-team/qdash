import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { QdashBotAvatar, UserAvatar } from "@/components/ui/UserAvatar";
import { startAvatarSpecSession, setAvatarSpec } from "@/lib/avatar/avatarSpecs";
import { automaticAvatarSpec, glyphAvatarDataUri } from "@/lib/avatar/glyphAvatar";

const listUserAvatars = vi.hoisted(() => vi.fn());

vi.mock("@/client/user-avatar/user-avatar", () => ({ listUserAvatars }));

const CUSTOM_SPEC = "v1:k3x9q2a-1.-2:p0w7zz:stripes:c";

function avatarSrc(name: string): string | null {
  return screen.getByRole("img", { name }).getAttribute("src");
}

function specsResponse(avatars: { username: string; spec: string }[]) {
  return { data: { avatars } };
}

describe("UserAvatar", () => {
  beforeEach(() => {
    startAvatarSpecSession(true);
    listUserAvatars.mockReset();
    listUserAvatars.mockResolvedValue(specsResponse([]));
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("renders the automatic avatar locally from the username at once", () => {
    listUserAvatars.mockReturnValue(new Promise(() => {}));
    render(<UserAvatar username="alice" size={32} />);

    const src = avatarSrc("alice");
    expect(src).toBe(glyphAvatarDataUri("v1:alice::solid:c"));
    expect(src?.startsWith("data:image/svg+xml")).toBe(true);
    expect(screen.getByRole("img", { name: "alice" }).getAttribute("width")).toBe("32");
  });

  it("titles the avatar with the username unless the caller opts out", () => {
    listUserAvatars.mockReturnValue(new Promise(() => {}));
    const { container, rerender } = render(<UserAvatar username="alice" />);
    expect(container.querySelector('[title="alice"]')).not.toBeNull();

    rerender(<UserAvatar username="alice" showTitle={false} />);
    expect(container.querySelector("[title]")).toBeNull();
  });

  it("gives the same username the same avatar in separate renders", () => {
    const { unmount } = render(<UserAvatar username="alice" />);
    const first = avatarSrc("alice");
    unmount();
    startAvatarSpecSession(true);
    render(<UserAvatar username="alice" />);
    expect(avatarSrc("alice")).toBe(first);
    render(<UserAvatar username="bob" />);
    expect(avatarSrc("bob")).not.toBe(first);
  });

  it("looks up every rendered user with one batched request and shows custom specs", async () => {
    listUserAvatars.mockResolvedValue(specsResponse([{ username: "bob", spec: CUSTOM_SPEC }]));
    render(
      <>
        <UserAvatar username="alice" />
        <UserAvatar username="bob" />
        <UserAvatar username="bob" size={20} />
      </>,
    );

    await waitFor(() =>
      expect(screen.getAllByRole("img", { name: "bob" })[0].getAttribute("src")).toBe(
        glyphAvatarDataUri(CUSTOM_SPEC),
      ),
    );
    expect(listUserAvatars).toHaveBeenCalledTimes(1);
    expect(listUserAvatars.mock.calls[0][0]).toEqual({ username: ["alice", "bob"] });
    expect(avatarSrc("alice")).toBe(glyphAvatarDataUri(automaticAvatarSpec("alice")));
  });

  it("keeps the automatic avatar, not initials, when the lookup fails", async () => {
    listUserAvatars.mockRejectedValue(new Error("Network Error"));
    render(<UserAvatar username="carol" />);

    await waitFor(() => expect(listUserAvatars).toHaveBeenCalledTimes(1));
    await act(async () => {});
    const image = screen.getByRole("img", { name: "carol" });
    expect(image.tagName).toBe("IMG");
    expect(image.getAttribute("src")).toBe(glyphAvatarDataUri("v1:carol::solid:c"));
  });

  it("ignores an invalid custom spec from the API", async () => {
    listUserAvatars.mockResolvedValue(specsResponse([{ username: "dave", spec: "<svg/>" }]));
    render(<UserAvatar username="dave" />);
    await waitFor(() => expect(listUserAvatars).toHaveBeenCalled());
    await act(async () => {});
    expect(avatarSrc("dave")).toBe(glyphAvatarDataUri("v1:dave::solid:c"));
  });

  it("updates every avatar of a user when a spec is saved in this tab", () => {
    render(
      <>
        <UserAvatar username="erin" />
        <UserAvatar username="erin" size={64} />
      </>,
    );
    act(() => setAvatarSpec("erin", CUSTOM_SPEC));
    for (const image of screen.getAllByRole("img", { name: "erin" })) {
      expect(image.getAttribute("src")).toBe(glyphAvatarDataUri(CUSTOM_SPEC));
    }
  });

  it("never requests an avatar image from the network", () => {
    render(<UserAvatar username="frank" />);
    for (const image of document.querySelectorAll("img")) {
      expect(image.getAttribute("src")).toMatch(/^data:image\/svg\+xml/);
    }
  });

  it("renders a placeholder without a lookup when there is no username", async () => {
    render(<UserAvatar username="" />);
    expect(screen.getByRole("img", { name: "User avatar" }).tagName).toBe("SPAN");
    expect(document.querySelector("img")).toBeNull();
    await act(async () => {});
    expect(listUserAvatars).not.toHaveBeenCalled();
  });

  it("keeps the OQTOPUS logo for the QDash bot", () => {
    render(<QdashBotAvatar />);
    expect(screen.getByRole("img", { name: "OQTOPUS" }).getAttribute("src")).toContain(
      "oqtopus_logo",
    );
  });
});
