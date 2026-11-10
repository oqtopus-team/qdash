import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GlyphAvatarPicker } from "@/components/ui/GlyphAvatarPicker";

describe("GlyphAvatarPicker", () => {
  afterEach(cleanup);

  it("renders the keyboard-operable picker with labelled actions", () => {
    render(
      <>
        <span id="avatar-label">Avatar</span>
        <GlyphAvatarPicker
          defaultValue="v1:alice::solid:c"
          onChange={vi.fn()}
          labelledBy="avatar-label"
        />
      </>,
    );

    const honeycomb = screen.getByRole("group", { name: "Avatar" });
    expect(honeycomb.getAttribute("tabindex")).toBe("0");
    expect(honeycomb.getAttribute("aria-describedby")).toBe("glyph-avatar-picker-hint");
    expect(screen.getByText(/use the arrow keys/)).toBeTruthy();
    for (const name of ["Shuffle", "New shape", "New colors", "New background"]) {
      expect(screen.getByRole("button", { name })).toBeTruthy();
    }
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
  });
});
