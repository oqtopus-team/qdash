import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CodeBlock } from "../CodeBlock";
import { ChatMarkdown } from "../ChatMarkdown";

vi.mock("mermaid", () => ({ default: { initialize: vi.fn(), render: vi.fn() } }));
vi.mock("@/contexts/ThemeContext", () => ({ useIsDarkTheme: () => false }));
const copyText = vi.hoisted(() => vi.fn());
vi.mock("@/lib/utils/clipboard", () => ({ copyText }));
vi.mock("@/components/ui/Toast", () => ({ useToast: () => ({ error: vi.fn() }) }));

afterEach(cleanup);

const highlighted = '[style*="--qd-code-"]';

// Highlights loads once per test file; these tests share it, as pages do.
describe("chat code with Highlights", () => {
  it("re-renders a saved answer with Highlights once it loads", async () => {
    const source =
      '```python\nx = "<b>&amp;</b>"  # **not bold\n```\n\n```zig-unknown\nraw <i>\n```';
    const { container } = render(<ChatMarkdown>{source}</ChatMarkdown>);
    await waitFor(() => expect(container.querySelector(`pre code ${highlighted}`)).not.toBeNull());

    const [python, unknown] = container.querySelectorAll("pre code");
    expect(python.querySelector(".hljs-comment")).toBeNull();
    expect(python.querySelector('[style*="--qd-code-comment"]')).toHaveTextContent("# **not bold");
    expect(python.textContent).toBe('x = "<b>&amp;</b>"  # **not bold\n');
    expect(container.querySelector("b, strong")).toBeNull();
    // Unknown languages stay plain text.
    expect(unknown.querySelector("span[style]")).toBeNull();
    expect(unknown.textContent).toBe("raw <i>\n");

    copyText.mockResolvedValue(undefined);
    fireEvent.click(screen.getAllByRole("button", { name: "Copy code" })[0]);
    expect(copyText).toHaveBeenCalledWith('x = "<b>&amp;</b>"  # **not bold\n');
  });

  it("highlights an open fence as it streams and keeps multi-line strings colored", async () => {
    const open = '```python\ns = """first\nsecond';
    const { container, rerender } = render(<ChatMarkdown streaming>{open}</ChatMarkdown>);
    await waitFor(() => expect(container.querySelector(`pre code ${highlighted}`)).not.toBeNull());

    rerender(<ChatMarkdown streaming>{`${open}\nthird"""\nprint(s)`}</ChatMarkdown>);
    const strings = [...container.querySelectorAll('pre code [style*="--qd-code-string"]')].map(
      (span) => span.textContent,
    );
    // Each line of the string is its own colored span, so every line keeps the color.
    expect(strings).toEqual(expect.arrayContaining(['"""first', "second", 'third"""']));
    expect(container.querySelector('pre [data-markdown="caret"]')).not.toBeNull();

    rerender(<ChatMarkdown>{`${open}\nthird"""\nprint(s)\n\`\`\`\n`}</ChatMarkdown>);
    expect(container.querySelector("pre code")?.textContent).toBe(
      's = """first\nsecond\nthird"""\nprint(s)\n',
    );
    expect(container.querySelector('[data-markdown="caret"]')).toBeNull();
  });

  it("highlights CodeBlock with the same palette, without hljs classes", async () => {
    const { container } = render(
      <CodeBlock language="yaml">{"qubit: Q00\nshots: 1024"}</CodeBlock>,
    );
    const code = container.querySelector("code.qd-code");
    await waitFor(() => expect(code?.querySelector(highlighted)).not.toBeNull());
    expect(code?.querySelector('[class^="hljs"]')).toBeNull();
    expect(code?.textContent).toBe("qubit: Q00\nshots: 1024");
  });
});
