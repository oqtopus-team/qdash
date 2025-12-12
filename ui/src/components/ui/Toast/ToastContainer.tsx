"use client";

import { FluentEmoji } from "@/components/ui/FluentEmoji";

import { useToastContext } from "./ToastContext";

const alertClass: Record<string, string> = {
  success: "alert-success",
  error: "alert-error",
  info: "alert-info",
  warning: "alert-warning",
};

const toastEmoji: Record<string, string> = {
  success: "success",
  error: "error",
  info: "info",
  warning: "warning",
};

export function ToastContainer() {
  const { toasts, removeToast } = useToastContext();

  if (toasts.length === 0) return null;

  return (
    <div className="toast toast-end toast-top z-50">
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className={`alert ${alertClass[toast.type]} cursor-pointer shadow-lg`}
          onClick={() => removeToast(toast.id)}
        >
          <FluentEmoji name={toastEmoji[toast.type]} size={20} />
          <span>{toast.message}</span>
        </div>
      ))}
    </div>
  );
}
