"use client";

import { Toaster } from "sonner";

import { DARK_THEMES } from "@/constants/themes";
import { useTheme } from "@/contexts/ThemeContext";
import { CircleCheck, CircleX, Info, TriangleAlert } from "lucide-react";

export function ToastContainer() {
  const { theme } = useTheme();

  return (
    <Toaster
      theme={DARK_THEMES.includes(theme) ? "dark" : "light"}
      position="top-right"
      duration={3000}
      closeButton
      icons={{
        success: <CircleCheck className="h-5 w-5" />,
        error: <CircleX className="h-5 w-5" />,
        info: <Info className="h-5 w-5" />,
        warning: <TriangleAlert className="h-5 w-5" />,
      }}
      toastOptions={{
        unstyled: true,
        classNames: {
          toast:
            "alert flex w-full items-center gap-2 rounded-xl border border-base-content/10 px-4 py-3 text-sm shadow-md",
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
