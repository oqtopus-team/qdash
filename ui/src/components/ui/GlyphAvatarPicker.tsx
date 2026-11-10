"use client";

import {
  AvatarPickerHoneycomb,
  AvatarPickerNewBackground,
  AvatarPickerNewColors,
  AvatarPickerNewShape,
  AvatarPickerRoot,
  AvatarPickerShuffle,
} from "glyph-avatar/react";
import type { CSSProperties } from "react";

const HINT_ID = "glyph-avatar-picker-hint";

// Draw the focus ring of the selected cell in the theme's content color.
const PICKER_STYLE = { "--ga-ring": "var(--color-base-content)" } as CSSProperties;
const ACTION_CLASS = "btn btn-ghost btn-sm btn-square";

/**
 * The glyph-avatar picker, styled with DaisyUI.
 *
 * `defaultValue` is the saved canonical spec; `onChange` receives the spec of the avatar the
 * user moves to or tweaks. The picker renders candidates locally from the pinned package; the
 * API renders and saves the chosen spec when the form is saved. Remount it with a new `key` to
 * discard a selection.
 */
export function GlyphAvatarPicker({
  defaultValue,
  onChange,
  labelledBy,
}: {
  defaultValue: string;
  onChange: (spec: string) => void;
  labelledBy?: string;
}) {
  return (
    <AvatarPickerRoot
      unstyled
      colors="curated"
      defaultValue={defaultValue}
      onChange={onChange}
      className="grid gap-2 overflow-hidden rounded-box border border-base-300 bg-base-100 p-2"
      style={PICKER_STYLE}
    >
      <AvatarPickerHoneycomb
        aria-labelledby={labelledBy}
        aria-describedby={HINT_ID}
        className="rounded-box focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary"
      />
      <p id={HINT_ID} className="px-1 text-xs text-base-content/60">
        Drag, swipe, or use the arrow keys to move between avatars. The centered avatar is selected.
      </p>
      <div className="flex flex-wrap items-center gap-1 border-t border-base-300 pt-2">
        <AvatarPickerShuffle className="btn btn-ghost btn-sm gap-2" />
        <div className="divider divider-horizontal mx-0" />
        <AvatarPickerNewShape className={ACTION_CLASS} />
        <AvatarPickerNewColors className={ACTION_CLASS} />
        <AvatarPickerNewBackground className={ACTION_CLASS} />
      </div>
    </AvatarPickerRoot>
  );
}
