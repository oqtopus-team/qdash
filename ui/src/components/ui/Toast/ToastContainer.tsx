"use client";

import { Toaster } from "sonner";

import { DARK_THEMES } from "@/constants/themes";
import { useTheme } from "@/contexts/ThemeContext";
import { CircleCheck, CircleX, Info, LoaderCircle, TriangleAlert, X } from "lucide-react";

// Toasts are unstyled so the DaisyUI theme owns the look: a neutral base surface with the status
// color carried by the icon. Sonner still supplies positioning, stacking and animation.
const STATUS_ICON_CLASS = "size-[18px]";

export function ToastContainer() {
  const { theme } = useTheme();

  return (
    <Toaster
      theme={DARK_THEMES.includes(theme) ? "dark" : "light"}
      position="top-right"
      duration={3000}
      closeButton
      icons={{
        success: <CircleCheck className={`${STATUS_ICON_CLASS} text-success`} />,
        error: <CircleX className={`${STATUS_ICON_CLASS} text-error`} />,
        info: <Info className={`${STATUS_ICON_CLASS} text-info`} />,
        warning: <TriangleAlert className={`${STATUS_ICON_CLASS} text-warning`} />,
        loading: (
          <LoaderCircle className={`${STATUS_ICON_CLASS} animate-spin text-base-content/60`} />
        ),
        close: <X className="size-3.5" />,
      }}
      toastOptions={{
        unstyled: true,
        classNames: {
          // Collapsed toasts behind the front one take its height, so hide their content the way
          // Sonner's styled mode does.
          toast:
            "flex w-full items-start gap-3 rounded-xl border border-base-content/10 bg-base-100 px-4 py-3 text-sm text-base-content shadow-md [&[data-expanded=false][data-front=false]>*]:opacity-0",
          // The icon slot is relative so Sonner's loader overlay stays inside it; a default toast
          // renders an empty slot, which is hidden.
          icon: "relative flex h-5 w-[18px] shrink-0 items-center justify-center empty:hidden",
          content: "flex min-w-0 flex-1 flex-col gap-0.5",
          title: "font-medium leading-5",
          description: "text-[13px] leading-5 text-base-content/70",
          actionButton: "btn btn-xs -my-0.5 shrink-0",
          cancelButton: "btn btn-ghost btn-xs -my-0.5 shrink-0",
          // Sonner renders the close button first; order-last moves it to the trailing edge.
          closeButton:
            "btn btn-ghost btn-xs btn-square order-last -my-0.5 -mr-1.5 shrink-0 text-base-content/60 hover:text-base-content",
        },
      }}
      containerAriaLabel="Notifications"
    />
  );
}
