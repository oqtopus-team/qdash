"use client";

import { useEffect } from "react";
import { Toaster, toast } from "@yusufceng1z/ding-react";

import { DARK_THEMES } from "@/constants/themes";
import { useTheme } from "@/contexts/ThemeContext";
import { useChatNotificationSettings } from "@/lib/chatNotificationSettings";

/**
 * The renderer of chat notifications (Ding), mounted once beside the app's other toasts.
 * It sits at the top center, apart from the app toasts at the top right, and takes its
 * colors from the DaisyUI theme (`.tst-viewport` in globals.css). Sound follows the user's
 * setting, off by default; Ding plays no sound for loading or progress toasts.
 */
export function ChatToaster() {
  const { theme } = useTheme();
  const { sound, volume } = useChatNotificationSettings();

  useEffect(() => {
    toast.configure({ sound, volume });
  }, [sound, volume]);

  return (
    <Toaster
      position="top-center"
      theme={DARK_THEMES.includes(theme) ? "dark" : "light"}
      labels={{ region: "Chat notifications", dismiss: "Dismiss chat notification" }}
    />
  );
}
