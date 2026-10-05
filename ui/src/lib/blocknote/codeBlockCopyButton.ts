import { createCodeBlockSpec } from "@blocknote/core";

type CodeBlockSpec = ReturnType<typeof createCodeBlockSpec>;
type CodeBlockRender = CodeBlockSpec["implementation"]["render"];

const COPY_ICON_SVG =
  '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>';

const CHECK_ICON_SVG =
  '<svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';

const COPIED_RESET_MS = 1500;

/** Creates a "copy code" button; call `destroy()` to remove its listeners. */
function createCopyButton(getCode: () => string): {
  button: HTMLButtonElement;
  destroy: () => void;
} {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "bn-code-block-copy-button";
  button.setAttribute("aria-label", "Copy code");
  button.setAttribute("contenteditable", "false");
  button.innerHTML = COPY_ICON_SVG;

  let resetTimer: ReturnType<typeof setTimeout> | undefined;

  const onMouseDown = (event: MouseEvent) => {
    event.preventDefault();
  };

  const onClick = () => {
    void navigator.clipboard.writeText(getCode()).then(() => {
      if (resetTimer) clearTimeout(resetTimer);
      button.innerHTML = CHECK_ICON_SVG;
      resetTimer = setTimeout(() => {
        button.innerHTML = COPY_ICON_SVG;
      }, COPIED_RESET_MS);
    });
  };

  button.addEventListener("mousedown", onMouseDown);
  button.addEventListener("click", onClick);

  return {
    button,
    destroy: () => {
      if (resetTimer) clearTimeout(resetTimer);
      button.removeEventListener("mousedown", onMouseDown);
      button.removeEventListener("click", onClick);
    },
  };
}

/** Adds a copy-to-clipboard button to every rendered code block. */
export function withCodeBlockCopyButton(spec: CodeBlockSpec): CodeBlockSpec {
  const originalRender = spec.implementation.render;

  function render(
    this: ThisParameterType<CodeBlockRender>,
    block: Parameters<CodeBlockRender>[0],
    editor: Parameters<CodeBlockRender>[1],
  ): ReturnType<CodeBlockRender> {
    const result = originalRender.call(this, block, editor);
    const codeElement = result.contentDOM;
    const { button, destroy: destroyButton } = createCopyButton(
      () => codeElement?.textContent ?? "",
    );
    result.dom.appendChild(button);

    const originalDestroy = result.destroy;
    return {
      ...result,
      destroy: () => {
        destroyButton();
        originalDestroy?.();
      },
    };
  }

  return {
    ...spec,
    implementation: {
      ...spec.implementation,
      render,
    },
  };
}
