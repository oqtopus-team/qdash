import { useSyncExternalStore } from "react";

/**
 * How chat notifications sound on this device: off unless the user turns it on in
 * **Settings → Copilot**, at a volume from 0 to 1. Kept in local storage; it holds no
 * user data and applies to whoever signs in on this browser.
 */
export interface ChatNotificationSettings {
  sound: boolean;
  volume: number;
}

const KEY = "qdash.chatNotifications.v1";
const CHANGED = "qdash:chat-notification-settings";
const DEFAULT_CHAT_NOTIFICATION_SETTINGS: ChatNotificationSettings = {
  sound: false,
  volume: 0.5,
};

function clampVolume(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value)
    ? Math.min(1, Math.max(0, value))
    : DEFAULT_CHAT_NOTIFICATION_SETTINGS.volume;
}

let cached: { raw: string | null; value: ChatNotificationSettings } | null = null;

export function readChatNotificationSettings(): ChatNotificationSettings {
  let raw: string | null = null;
  try {
    raw = typeof window === "undefined" ? null : window.localStorage.getItem(KEY);
  } catch {
    raw = null;
  }
  // The same object while nothing changed, as useSyncExternalStore needs.
  if (cached && cached.raw === raw) return cached.value;
  let value = DEFAULT_CHAT_NOTIFICATION_SETTINGS;
  if (raw) {
    try {
      const parsed = JSON.parse(raw) as { sound?: unknown; volume?: unknown };
      value = { sound: parsed.sound === true, volume: clampVolume(parsed.volume) };
    } catch {
      value = DEFAULT_CHAT_NOTIFICATION_SETTINGS;
    }
  }
  cached = { raw, value };
  return value;
}

export function writeChatNotificationSettings(patch: Partial<ChatNotificationSettings>): void {
  const next = { ...readChatNotificationSettings(), ...patch };
  try {
    window.localStorage.setItem(
      KEY,
      JSON.stringify({ sound: next.sound === true, volume: clampVolume(next.volume) }),
    );
  } catch {
    // Storage is off: the setting lasts until the page reloads.
    cached = { raw: null, value: next };
  }
  window.dispatchEvent(new Event(CHANGED));
}

function subscribe(onChange: () => void): () => void {
  window.addEventListener(CHANGED, onChange);
  window.addEventListener("storage", onChange);
  return () => {
    window.removeEventListener(CHANGED, onChange);
    window.removeEventListener("storage", onChange);
  };
}

const serverSettings = () => DEFAULT_CHAT_NOTIFICATION_SETTINGS;

export function useChatNotificationSettings(): ChatNotificationSettings {
  return useSyncExternalStore(subscribe, readChatNotificationSettings, serverSettings);
}
