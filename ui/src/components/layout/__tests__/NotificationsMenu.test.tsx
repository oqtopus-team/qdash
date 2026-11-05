import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NotificationsMenu } from "@/components/layout/NotificationsMenu";

const markRead = vi.fn();
const markAllRead = vi.fn();

let unreadCount = 0;
let notifications: Array<{
  id: string;
  title: string;
  excerpt?: string;
  actor_username: string;
  target_url: string;
  read_at: string | null;
  created_at: string;
}> = [];
const listCalls: boolean[] = [];

// Plain anchor stand-in; navigation is prevented because jsdom cannot follow links.
vi.mock("next/link", () => ({
  default: ({ children, href, onClick, ...props }: React.ComponentProps<"a">) => (
    <a
      href={href}
      onClick={(event) => {
        onClick?.(event);
        event.preventDefault();
      }}
      {...props}
    >
      {children}
    </a>
  ),
}));

vi.mock("@/hooks/useNotifications", () => ({
  useUnreadNotificationCount: () => ({ data: { data: { unread_count: unreadCount } } }),
  useNotifications: (_unreadOnly: boolean, options?: { enabled?: boolean }) => {
    listCalls.push(options?.enabled ?? true);
    return { data: { data: { notifications, unread_count: unreadCount } }, isLoading: false };
  },
  useNotificationActions: () => ({
    markRead: { mutate: markRead },
    markAllRead: { mutate: markAllRead, isPending: false },
  }),
}));

describe("NotificationsMenu", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    unreadCount = 0;
    notifications = [];
    listCalls.length = 0;
  });

  it("shows the unread count on the bell and defers the list until opened", () => {
    unreadCount = 3;
    render(<NotificationsMenu />);

    const trigger = screen.getByRole("button", { name: "Notifications, 3 unread" });
    expect(trigger.textContent).toBe("3");
    expect(listCalls.every((enabled) => enabled === false)).toBe(true);
  });

  it("hides the badge when nothing is unread", () => {
    render(<NotificationsMenu />);

    const trigger = screen.getByRole("button", { name: "Notifications" });
    expect(trigger.textContent).toBe("");
  });

  it("lists recent notifications, marks one read on open, and links to the inbox", async () => {
    unreadCount = 1;
    notifications = [
      {
        id: "n-1",
        title: "Reply on T1 result",
        excerpt: "Looks good to me",
        actor_username: "alice",
        target_url: "/forum/thread-1",
        read_at: null,
        created_at: new Date().toISOString(),
      },
      {
        id: "n-2",
        title: "Mention in note",
        actor_username: "bob",
        target_url: "/chip/note-2",
        read_at: new Date().toISOString(),
        created_at: new Date().toISOString(),
      },
    ];
    render(<NotificationsMenu />);

    fireEvent.pointerDown(screen.getByRole("button", { name: "Notifications, 1 unread" }));
    await waitFor(() => expect(screen.getByText("Reply on T1 result")).toBeTruthy());
    expect(listCalls[listCalls.length - 1]).toBe(true);
    expect(screen.getByText("Mention in note")).toBeTruthy();
    expect(screen.getByRole("menuitem", { name: "View all" }).getAttribute("href")).toBe("/inbox");

    fireEvent.click(screen.getByRole("button", { name: "Mark all read" }));
    expect(markAllRead).toHaveBeenCalledTimes(1);

    // Selecting an item closes the menu, so this comes last.
    fireEvent.click(screen.getByText("Reply on T1 result"));
    expect(markRead).toHaveBeenCalledWith({ notificationId: "n-1" });
  });

  it("shows the caught-up message when there are no notifications", async () => {
    render(<NotificationsMenu />);

    fireEvent.pointerDown(screen.getByRole("button", { name: "Notifications" }));
    await waitFor(() => expect(screen.getByText("You are all caught up")).toBeTruthy());
    expect(
      (screen.getByRole("button", { name: "Mark all read" }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });
});
