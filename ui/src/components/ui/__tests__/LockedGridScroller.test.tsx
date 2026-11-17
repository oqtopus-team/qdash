import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { LockedGridScroller } from "../LockedGridScroller";

describe("LockedGridScroller", () => {
  afterEach(cleanup);

  it("scrolls its content and keeps it centered while it fits", () => {
    render(
      <LockedGridScroller>
        <div data-testid="grid" />
      </LockedGridScroller>,
    );

    const scroller = screen.getByTestId("grid").parentElement;
    expect(scroller).toHaveClass("overflow-auto", "justify-center-safe", "items-start");
    expect(scroller).toHaveClass("min-w-0", "min-h-0", "flex-1", "self-stretch");
  });
});
