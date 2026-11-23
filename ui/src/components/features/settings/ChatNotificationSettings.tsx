"use client";

import { Volume2 } from "lucide-react";
import { chime } from "@yusufceng1z/ding";

import {
  useChatNotificationSettings,
  writeChatNotificationSettings,
} from "@/lib/chatNotificationSettings";

/**
 * Whether chat notifications play a sound on this device, and how loud. Off by default;
 * the toasts themselves always show.
 */
export function ChatNotificationSettings() {
  const { sound, volume } = useChatNotificationSettings();
  const percent = Math.round(volume * 100);

  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-sm font-medium">Chat notifications</h3>
      <p id="chat-notification-help" className="text-sm text-base-content/60">
        A notification appears when an answer is ready, needs your approval or answer, waits for an
        expert, or fails, unless that chat is already on screen. Sound is off unless you turn it on;
        it applies to this browser only.
      </p>
      <label className="choice-field w-fit gap-3">
        <input
          type="checkbox"
          className="toggle toggle-sm"
          checked={sound}
          onChange={(event) => writeChatNotificationSettings({ sound: event.target.checked })}
          aria-describedby="chat-notification-help"
        />
        <span className="text-sm">Play a sound</span>
      </label>
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <label htmlFor="chat-notification-volume" className="text-sm text-base-content/70">
          Volume
        </label>
        <input
          id="chat-notification-volume"
          type="range"
          min={0}
          max={100}
          step={5}
          value={percent}
          disabled={!sound}
          onChange={(event) =>
            writeChatNotificationSettings({ volume: Number(event.target.value) / 100 })
          }
          className="range range-xs w-full sm:max-w-xs"
          aria-valuetext={`${percent}%`}
        />
        <span className="w-10 text-xs tabular-nums text-base-content/60" aria-hidden="true">
          {percent}%
        </span>
        <button
          type="button"
          className="btn btn-sm btn-ghost w-fit"
          disabled={!sound}
          onClick={() => chime("success", volume)}
        >
          <Volume2 data-icon="inline-start" aria-hidden="true" />
          Preview
        </button>
      </div>
    </div>
  );
}
