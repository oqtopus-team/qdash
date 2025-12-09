"use client";

import { useEffect } from "react";

interface ToastProps {
  message: string;
  duration?: number;
  onClose: () => void;
}

export function Toast({ message, duration = 2000, onClose }: ToastProps) {
  useEffect(() => {
    const timer = setTimeout(() => {
      onClose();
    }, duration);

    return () => clearTimeout(timer);
  }, [duration, onClose]);

  return (
    <div className="toast toast-end">
      <div className="alert alert-success">
        <span>{message}</span>
      </div>
    </div>
  );
}
