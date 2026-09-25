"use client";

import { useSyncExternalStore } from "react";

const subscribe = () => () => {};

export function SelectedLabel() {
  const isHydrated = useSyncExternalStore(
    subscribe,
    () => true,
    () => false,
  );

  if (!isHydrated) return null;

  return (
    <button type="button">
      <selectedcontent />
    </button>
  );
}
