import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GlobalCommandPalette } from "@/components/layout/GlobalCommandPalette";

const push = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { system_role: "user" } }),
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ canEdit: false }),
}));

describe("GlobalCommandPalette", () => {
  afterEach(() => {
    cleanup();
    push.mockReset();
  });

  it("opens with the platform shortcut and navigates to a selected page", () => {
    render(<GlobalCommandPalette />);

    fireEvent.keyDown(window, { key: "k", metaKey: true });

    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getByRole("combobox", { name: "QDash navigation" })).toBeTruthy();

    fireEvent.click(screen.getByRole("option", { name: "Dashboard" }));

    expect(push).toHaveBeenCalledWith("/dashboard");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("hides pages unavailable to the current user", () => {
    render(<GlobalCommandPalette />);
    fireEvent.click(screen.getByRole("button", { name: "Open navigation search" }));

    expect(screen.queryByRole("option", { name: "Workflow" })).toBeNull();
    expect(screen.queryByRole("option", { name: "Admin" })).toBeNull();
    expect(screen.getByRole("option", { name: "Settings" })).toBeTruthy();
  });
});
