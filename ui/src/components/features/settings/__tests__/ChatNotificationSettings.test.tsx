import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatNotificationSettings } from "@/components/features/settings/ChatNotificationSettings";
import { readChatNotificationSettings } from "@/lib/chatNotificationSettings";

const chime = vi.hoisted(() => vi.fn());
vi.mock("@yusufceng1z/ding", () => ({ chime }));

afterEach(() => {
  cleanup();
  localStorage.clear();
  chime.mockClear();
});

describe("chat notification sound", () => {
  it("is off by default, with volume and preview disabled", () => {
    expect(readChatNotificationSettings()).toEqual({ sound: false, volume: 0.5 });
    render(<ChatNotificationSettings />);
    expect(screen.getByRole("checkbox", { name: "Play a sound" })).not.toBeChecked();
    expect(screen.getByRole("slider", { name: "Volume" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Preview" })).toBeDisabled();
  });

  it("plays only when the user turns it on, at the chosen volume", () => {
    render(<ChatNotificationSettings />);
    fireEvent.click(screen.getByRole("checkbox", { name: "Play a sound" }));
    fireEvent.change(screen.getByRole("slider", { name: "Volume" }), { target: { value: "20" } });
    expect(readChatNotificationSettings()).toEqual({ sound: true, volume: 0.2 });
    expect(chime).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Preview" }));
    expect(chime).toHaveBeenCalledWith("success", 0.2);
  });

  it("reads a damaged setting as the defaults", () => {
    localStorage.setItem("qdash.chatNotifications.v1", '{"sound":"yes","volume":7}');
    expect(readChatNotificationSettings()).toEqual({ sound: false, volume: 1 });
  });
});
