import { cleanup, render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { afterEach, describe, expect, it } from "vitest";

import { AnimatedNumber, AnimatedText } from "@/components/ui/AnimatedNumber";

afterEach(cleanup);

describe("AnimatedNumber", () => {
  it("exposes one plain-text phrase and hides the animated copy", () => {
    const { container, rerender } = render(
      <AnimatedText label="4 / 12 points">
        <AnimatedNumber value={4} /> / <AnimatedNumber value={12} /> points
      </AnimatedText>,
    );

    expect(screen.getByText("4 / 12 points")).toHaveClass("sr-only");
    const flows = container.querySelectorAll("number-flow-react");
    expect(flows).toHaveLength(2);
    flows.forEach((flow) => expect(flow.closest("[aria-hidden='true']")).not.toBeNull());

    rerender(
      <AnimatedText label="5 / 12 points">
        <AnimatedNumber value={5} /> / <AnimatedNumber value={12} /> points
      </AnimatedText>,
    );
    expect(screen.getByText("5 / 12 points")).toBeInTheDocument();
    expect(screen.queryByText("4 / 12 points")).toBeNull();
  });

  it("keeps reduced-motion support enabled", () => {
    const { container } = render(<AnimatedNumber value={33} suffix="%" />);
    const flow = container.querySelector("number-flow-react") as
      | (Element & { respectMotionPreference?: boolean })
      | null;
    expect(flow?.respectMotionPreference).toBe(true);
  });

  it("renders the final value on the server without locale grouping", () => {
    const html = renderToString(<AnimatedNumber value={1200} suffix="%" />);
    expect(html).toContain('aria-label="1200%"');
    expect(html).not.toContain("1,200");
  });
});
