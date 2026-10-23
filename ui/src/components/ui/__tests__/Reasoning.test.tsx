import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { Loader } from "../Loader";
import { Reasoning, ReasoningContent, ReasoningTrigger } from "../Reasoning";

afterEach(cleanup);

function Block({ streaming, defaultOpen }: { streaming: boolean; defaultOpen?: boolean }) {
  return (
    <Reasoning isStreaming={streaming} defaultOpen={defaultOpen}>
      <ReasoningTrigger>Thought</ReasoningTrigger>
      <ReasoningContent>
        <p>the reasoning text</p>
      </ReasoningContent>
    </Reasoning>
  );
}

function content() {
  return screen.getByText("the reasoning text").parentElement!.parentElement!;
}

describe("Reasoning", () => {
  it("starts closed and toggles from the trigger", () => {
    render(<Block streaming={false} />);
    expect(content().getAttribute("aria-hidden")).toBe("true");
    expect(screen.getByRole("button", { name: /Thought/ }).getAttribute("aria-expanded")).toBe(
      "false",
    );

    fireEvent.click(screen.getByRole("button", { name: /Thought/ }));
    expect(content().getAttribute("aria-hidden")).toBe("false");
    expect(content().style.maxHeight).not.toBe("0px");
  });

  it("opens while streaming and closes again when the stream ends", () => {
    const { rerender } = render(<Block streaming />);
    expect(content().getAttribute("aria-hidden")).toBe("false");

    rerender(<Block streaming={false} />);
    expect(content().getAttribute("aria-hidden")).toBe("true");
    expect(content().style.maxHeight).toBe("0px");
  });

  it("respects defaultOpen when nothing streams", () => {
    render(<Block streaming={false} defaultOpen />);
    expect(content().getAttribute("aria-hidden")).toBe("false");
  });
});

describe("Loader", () => {
  it("renders the text variants with their label and the dot variants with a status role", () => {
    render(<Loader variant="text-shimmer" text="Running CheckRabi" />);
    expect(screen.getByText("Running CheckRabi").className).toContain("loader-text-shimmer");
    cleanup();
    render(<Loader variant="typing" />);
    expect(screen.getByRole("status")).toBeTruthy();
    expect(screen.getByText("Loading").className).toContain("sr-only");
  });
});
