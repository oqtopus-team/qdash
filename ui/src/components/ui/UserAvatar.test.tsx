import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { QdashBotAvatar, UserAvatar } from "@/components/ui/UserAvatar";
import { setAvatarVersion } from "@/lib/avatar/avatarVersions";

describe("UserAvatar", () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("loads the saved avatar image from the same-origin avatar route", () => {
    render(<UserAvatar username="alice" size={32} />);
    const image = screen.getByRole("img", { name: "alice" });
    expect(image.getAttribute("src")).toMatch(
      /^(http:\/\/localhost:\d+)?\/api\/users\/alice\/avatar$/,
    );
    expect(image.getAttribute("width")).toBe("32");
    expect(document.querySelector('img[src*="/avatars/"]')).toBeNull();
  });

  it("requests the new image when the avatar is saved in this tab", () => {
    render(<UserAvatar username="bob" />);
    act(() => setAvatarVersion("bob", "etag-2"));
    expect(screen.getByRole("img", { name: "bob" }).getAttribute("src")).toMatch(
      /\/api\/users\/bob\/avatar\?v=etag-2$/,
    );
  });

  it("falls back to an initial when the image cannot be loaded", () => {
    render(<UserAvatar username="carol" />);
    fireEvent.error(screen.getByRole("img", { name: "carol" }));
    const placeholder = screen.getByRole("img", { name: "carol" });
    expect(placeholder.tagName).toBe("SPAN");
    expect(placeholder.textContent).toBe("C");
  });

  it("renders a placeholder without a request when there is no username", () => {
    render(<UserAvatar username="" />);
    expect(screen.getByRole("img", { name: "User avatar" }).tagName).toBe("SPAN");
    expect(document.querySelector("img")).toBeNull();
  });

  it("recovers from a transient failure without remounting the avatar", () => {
    vi.useFakeTimers();
    render(<UserAvatar username="retry-user" />);
    fireEvent.error(screen.getByRole("img", { name: "retry-user" }));
    act(() => vi.advanceTimersByTime(1000));
    const image = screen.getByRole("img", { name: "retry-user" });
    expect(image.tagName).toBe("IMG");
    expect(image.getAttribute("src")).toContain("?retry=1");
    fireEvent.load(image);
    act(() => vi.advanceTimersByTime(10000));
    expect(screen.getByRole("img", { name: "retry-user" })).toBe(image);
  });

  it("stops after two retries and starts fresh when the source changes", () => {
    vi.useFakeTimers();
    const { rerender } = render(<UserAvatar username="offline-user" />);
    fireEvent.error(screen.getByRole("img", { name: "offline-user" }));
    act(() => vi.advanceTimersByTime(1000));
    fireEvent.error(screen.getByRole("img", { name: "offline-user" }));
    act(() => vi.advanceTimersByTime(3000));
    expect(screen.getByRole("img", { name: "offline-user" }).getAttribute("src")).toContain(
      "?retry=2",
    );
    fireEvent.error(screen.getByRole("img", { name: "offline-user" }));
    act(() => vi.advanceTimersByTime(10000));
    expect(screen.getByRole("img", { name: "offline-user" }).tagName).toBe("SPAN");
    expect(vi.getTimerCount()).toBe(0);
    rerender(<UserAvatar username="new-user" />);
    expect(screen.getByRole("img", { name: "new-user" }).getAttribute("src")).not.toContain(
      "retry=",
    );
  });

  it("cancels a pending retry when the avatar unmounts", () => {
    vi.useFakeTimers();
    const { unmount } = render(<UserAvatar username="unmount-user" />);
    fireEvent.error(screen.getByRole("img", { name: "unmount-user" }));
    expect(vi.getTimerCount()).toBe(1);
    unmount();
    expect(vi.getTimerCount()).toBe(0);
  });

  it("keeps the OQTOPUS logo for the QDash bot", () => {
    render(<QdashBotAvatar />);
    expect(screen.getByRole("img", { name: "OQTOPUS" }).getAttribute("src")).toContain(
      "oqtopus_logo",
    );
  });
});
