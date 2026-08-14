import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";

describe("DialogContent", () => {
  afterEach(() => cleanup());

  it("allows callers to override conflicting layout classes", () => {
    render(
      <Dialog open>
        <DialogContent className="max-w-[112rem] overflow-hidden rounded-none">
          <DialogTitle>Task history</DialogTitle>
          <DialogDescription>History details</DialogDescription>
        </DialogContent>
      </Dialog>,
    );

    const dialog = screen.getByRole("dialog");
    expect(dialog.className).toContain("max-w-[112rem]");
    expect(dialog.className).toContain("overflow-hidden");
    expect(dialog.className).toContain("rounded-none");
    expect(dialog.className).not.toContain("max-w-lg");
    expect(dialog.className).not.toContain("overflow-y-auto");
    expect(dialog.className).not.toContain("rounded-3xl");
  });
});
