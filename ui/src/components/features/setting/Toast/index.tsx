"use client";

import { useEffect } from "react";

interface ToastProps {
  message: string;
  duration?: number;
  type?: "success" | "error" | "info" | "warning";
  onClose: () => void;
}

export function Toast({
  message,
  duration = 2000,
  type = "success",
  onClose,
}: ToastProps) {
  useEffect(() => {
    const timer = setTimeout(() => {
      onClose();
    }, duration);

    return () => clearTimeout(timer);
  }, [duration, onClose]);

  const alertClass = {
    success: "alert-success",
    error: "alert-error",
    info: "alert-info",
    warning: "alert-warning",
  }[type];

  return (
    <div className="toast toast-end">
      <div className={`alert ${alertClass}`}>
        <span>{message}</span>
      </div>
    </div>
  );
}
