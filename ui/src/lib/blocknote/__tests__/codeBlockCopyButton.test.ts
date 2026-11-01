import { createCodeBlockSpec } from "@blocknote/core";
import { afterEach, describe, expect, it, vi } from "vitest";

import { withCodeBlockCopyButton } from "../codeBlockCopyButton";

const { toastErrorMock } = vi.hoisted(() => ({
  toastErrorMock: vi.fn(),
}));

vi.mock("sonner", () => ({
  toast: { error: toastErrorMock },
}));

/** Stubs `navigator.clipboard.writeText` with the given mock, leaving other `navigator` properties untouched. */
function mockClipboard(writeText: ReturnType<typeof vi.fn>) {
  vi.stubGlobal(
    "navigator",
    new Proxy(navigator, {
      get(target, property) {
        if (property === "clipboard") return { writeText };
        return Reflect.get(target, property, target);
      },
    }),
  );
}

/** Stubs `navigator.clipboard` as `undefined`, simulating a non-secure context. */
function mockMissingClipboard() {
  vi.stubGlobal(
    "navigator",
    new Proxy(navigator, {
      get(target, property) {
        if (property === "clipboard") return undefined;
        return Reflect.get(target, property, target);
      },
    }),
  );
}

type FakeRenderResult = { dom: HTMLElement; contentDOM: HTMLElement; destroy?: () => void };
type FakeRender = (block: unknown, editor: unknown) => FakeRenderResult;

/** Wraps a stub `render` (returning `renderResult`) the same way `codeBlock.ts` wraps the real one. */
function buildWrappedRender(renderResult: FakeRenderResult): FakeRender {
  const base = createCodeBlockSpec();
  const spec = {
    ...base,
    implementation: {
      ...base.implementation,
      render: () => renderResult,
    },
  };
  const wrapped = withCodeBlockCopyButton(spec);
  return wrapped.implementation.render as unknown as FakeRender;
}

describe("withCodeBlockCopyButton", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    toastErrorMock.mockReset();
  });

  it("appends a copy button to the rendered dom", () => {
    const dom = document.createElement("div");
    const code = document.createElement("code");
    code.textContent = "print('hi')";
    dom.appendChild(code);

    const result = buildWrappedRender({ dom, contentDOM: code })(undefined, undefined);

    const button = result.dom.querySelector(".bn-code-block-copy-button");
    expect(button).not.toBeNull();
    expect(button?.getAttribute("type")).toBe("button");
    expect(button?.getAttribute("aria-label")).toBe("Copy code");
    expect(button?.getAttribute("contenteditable")).toBe("false");
  });

  it("copies the content DOM's current text when clicked", async () => {
    const dom = document.createElement("div");
    const code = document.createElement("code");
    code.textContent = "print('hi')";
    dom.appendChild(code);

    const writeText = vi.fn().mockResolvedValue(undefined);
    mockClipboard(writeText);

    const result = buildWrappedRender({ dom, contentDOM: code })(undefined, undefined);

    // Edited after render — the button should read the live text, not a snapshot.
    code.textContent = "print('bye')";

    result.dom.querySelector<HTMLButtonElement>(".bn-code-block-copy-button")?.click();
    await Promise.resolve();

    expect(writeText).toHaveBeenCalledWith("print('bye')");
  });

  it("prevents the default mousedown so the editor selection is not disturbed", () => {
    const dom = document.createElement("div");
    const code = document.createElement("code");
    dom.appendChild(code);

    const result = buildWrappedRender({ dom, contentDOM: code })(undefined, undefined);
    const button = result.dom.querySelector<HTMLButtonElement>(".bn-code-block-copy-button");
    const event = new MouseEvent("mousedown", { bubbles: true, cancelable: true });

    button?.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
  });

  it("shows an error toast and keeps the copy icon when writeText rejects", async () => {
    const dom = document.createElement("div");
    const code = document.createElement("code");
    code.textContent = "print('hi')";
    dom.appendChild(code);

    const writeText = vi.fn().mockRejectedValue(new Error("denied"));
    mockClipboard(writeText);

    const result = buildWrappedRender({ dom, contentDOM: code })(undefined, undefined);
    const button = result.dom.querySelector<HTMLButtonElement>(".bn-code-block-copy-button");
    const copyIcon = button?.innerHTML;

    button?.click();
    await Promise.resolve();
    await Promise.resolve();

    expect(button?.innerHTML).toBe(copyIcon);
    expect(toastErrorMock).toHaveBeenCalledWith("Failed to copy code");
  });

  it("shows an error toast when navigator.clipboard is unavailable", async () => {
    const dom = document.createElement("div");
    const code = document.createElement("code");
    code.textContent = "print('hi')";
    dom.appendChild(code);

    mockMissingClipboard();

    const result = buildWrappedRender({ dom, contentDOM: code })(undefined, undefined);
    const button = result.dom.querySelector<HTMLButtonElement>(".bn-code-block-copy-button");
    const copyIcon = button?.innerHTML;

    button?.click();
    await Promise.resolve();
    await Promise.resolve();

    expect(button?.innerHTML).toBe(copyIcon);
    expect(toastErrorMock).toHaveBeenCalledWith("Failed to copy code");
  });

  it("chains the original destroy callback", () => {
    const dom = document.createElement("div");
    const code = document.createElement("code");
    dom.appendChild(code);
    const originalDestroy = vi.fn();

    const result = buildWrappedRender({ dom, contentDOM: code, destroy: originalDestroy })(
      undefined,
      undefined,
    );
    result.destroy?.();

    expect(originalDestroy).toHaveBeenCalledOnce();
  });
});
