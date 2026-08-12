import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/Tooltip";

describe("Tooltip", () => {
  afterEach(() => cleanup());

  it("renders accessible portal content for a trigger", () => {
    render(
      <Tooltip open>
        <TooltipTrigger asChild>
          <button type="button">Zoom in</button>
        </TooltipTrigger>
        <TooltipContent className="max-w-96">Increase the grid scale</TooltipContent>
      </Tooltip>,
    );

    const trigger = screen.getByRole("button", { name: "Zoom in" });
    const tooltip = screen.getByRole("tooltip");
    expect(document.body.contains(tooltip)).toBe(true);
    expect(trigger.getAttribute("aria-describedby")).toBe(tooltip.id);
    expect(tooltip.className).toContain("max-w-96");
    expect(tooltip.className).not.toContain("max-w-72");
  });
});
