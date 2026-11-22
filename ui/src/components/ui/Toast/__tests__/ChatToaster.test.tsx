import { act, cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChatToaster } from "@/components/ui/Toast/ChatToaster";
import { writeChatNotificationSettings } from "@/lib/chatNotificationSettings";

const ding = vi.hoisted(() => ({ configure: vi.fn(), props: [] as unknown[] }));
vi.mock("@yusufceng1z/ding-react", () => ({
  Toaster: (props: unknown) => {
    ding.props.push(props);
    return null;
  },
  toast: { configure: ding.configure },
}));
vi.mock("@/contexts/ThemeContext", () => ({ useTheme: () => ({ theme: "dark" }) }));

afterEach(() => {
  cleanup();
  localStorage.clear();
  ding.configure.mockClear();
});

describe("the chat toaster", () => {
  it("plays no sound unless the user turned it on", () => {
    render(<ChatToaster />);
    expect(ding.configure).toHaveBeenLastCalledWith({ sound: false, volume: 0.5 });
    expect(ding.props[ding.props.length - 1]).toMatchObject({
      position: "top-center",
      theme: "dark",
      labels: { region: "Chat notifications" },
    });
    act(() => writeChatNotificationSettings({ sound: true, volume: 0.3 }));
    expect(ding.configure).toHaveBeenLastCalledWith({ sound: true, volume: 0.3 });
  });
});
