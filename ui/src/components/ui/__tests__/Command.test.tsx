import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/Command";

describe("Command", () => {
  afterEach(() => cleanup());

  it("filters and selects commands", () => {
    const onSelect = vi.fn();

    render(
      <Command label="Search commands">
        <CommandInput />
        <CommandList>
          <CommandEmpty>No commands found</CommandEmpty>
          <CommandItem value="Save Flow" onSelect={onSelect}>
            Save Flow
          </CommandItem>
          <CommandItem value="Execute Flow">Execute Flow</CommandItem>
        </CommandList>
      </Command>,
    );

    fireEvent.change(screen.getByRole("combobox", { name: "Search commands" }), {
      target: { value: "save" },
    });

    expect(screen.getByText("Save Flow")).toBeTruthy();
    expect(screen.queryByText("Execute Flow")).toBeNull();

    fireEvent.click(screen.getByText("Save Flow"));
    expect(onSelect).toHaveBeenCalledOnce();
  });

  it("renders dialog content in a portal", () => {
    render(
      <CommandDialog
        open
        onOpenChange={vi.fn()}
        title="Quick actions"
        description="Search available actions"
      >
        <Command>Commands</Command>
      </CommandDialog>,
    );

    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getByText("Quick actions")).toBeTruthy();
    expect(screen.getByText("Search available actions")).toBeTruthy();
  });
});
