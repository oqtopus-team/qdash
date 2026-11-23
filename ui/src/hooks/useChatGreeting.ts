"use client";

import { useEffect, useState } from "react";

/** Use the viewer's local time after hydration, and refresh while the chat stays open. */
export function useChatGreeting(name?: string | null): string {
  const [greeting, setGreeting] = useState("Hello");

  useEffect(() => {
    const update = () => {
      const hour = new Date().getHours();
      setGreeting(
        hour >= 5 && hour < 12
          ? "Good morning"
          : hour >= 12 && hour < 18
            ? "Good afternoon"
            : "Good evening",
      );
    };
    update();
    const timer = window.setInterval(update, 60_000);
    window.addEventListener("focus", update);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("focus", update);
    };
  }, []);

  const displayName = name?.trim();
  return displayName ? `${greeting}, ${displayName}` : greeting;
}
