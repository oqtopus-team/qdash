import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/DropdownMenu";

describe("DropdownMenu", () => {
  afterEach(() => cleanup());

  it("renders menu content in a portal with shared styles", () => {
    render(
      <DropdownMenu open>
        <DropdownMenuTrigger>Actions</DropdownMenuTrigger>
        <DropdownMenuContent className="min-w-72">
          <DropdownMenuItem>View execution</DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>,
    );

    const menu = screen.getByRole("menu");
    expect(document.body.contains(menu)).toBe(true);
    expect(menu.className).toContain("min-w-72");
    expect(menu.className).not.toContain("min-w-48");
    expect(screen.getByRole("menuitem", { name: "View execution" })).toBeTruthy();
  });

  it("exposes checkbox state for multi-select menus", () => {
    const onCheckedChange = vi.fn();
    render(
      <DropdownMenu open>
        <DropdownMenuTrigger>Labels</DropdownMenuTrigger>
        <DropdownMenuContent>
          <DropdownMenuCheckboxItem checked onCheckedChange={onCheckedChange}>
            Calibration
          </DropdownMenuCheckboxItem>
        </DropdownMenuContent>
      </DropdownMenu>,
    );

    expect(
      screen.getByRole("menuitemcheckbox", { name: "Calibration" }).getAttribute("aria-checked"),
    ).toBe("true");
  });
});
