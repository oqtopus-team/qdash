"use client";

import { Toaster } from "sonner";

import { DARK_THEMES } from "@/constants/themes";
import { useTheme } from "@/contexts/ThemeContext";
import { FluentEmoji } from "@/components/ui/FluentEmoji";

export function ToastContainer() {
  const { theme } = useTheme();

  return (
    <Toaster
      theme={DARK_THEMES.includes(theme) ? "dark" : "light"}
      position="top-right"
      duration={3000}
      closeButton
      icons={{
        success: <FluentEmoji name="success" size={20} />,
        error: <FluentEmoji name="error" size={20} />,
        info: <FluentEmoji name="info" size={20} />,
        warning: <FluentEmoji name="warning" size={20} />,
      }}
      toastOptions={{
        unstyled: true,
        classNames: {
          toast:
            "alert flex w-full items-center gap-2 rounded-xl border border-base-content/10 px-4 py-3 text-sm shadow-lg",
          success: "alert-success",
          error: "alert-error",
          info: "alert-info",
          warning: "alert-warning",
          content: "min-w-0 flex-1",
          closeButton: "btn btn-xs btn-circle btn-ghost shrink-0",
        },
      }}
      containerAriaLabel="Notifications"
    />
  );
}
