"use client";

import { useCallback } from "react";
import { useToastContext } from "./ToastContext";

export function useToast() {
  const { addToast } = useToastContext();

  const success = useCallback(
    (message: string) => addToast(message, "success"),
    [addToast],
  );

  const error = useCallback(
    (message: string) => addToast(message, "error"),
    [addToast],
  );

  const info = useCallback(
    (message: string) => addToast(message, "info"),
    [addToast],
  );

  const warning = useCallback(
    (message: string) => addToast(message, "warning"),
    [addToast],
  );

  return { success, error, info, warning };
}
