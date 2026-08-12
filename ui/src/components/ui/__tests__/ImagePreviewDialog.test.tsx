import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ImagePreviewDialog } from "@/components/ui/ImagePreviewDialog";

afterEach(cleanup);

describe("ImagePreviewDialog", () => {
  it("renders only when an image source is provided", () => {
    const { rerender } = render(<ImagePreviewDialog src={null} onClose={vi.fn()} />);
    expect(screen.queryByRole("dialog")).toBeNull();

    rerender(<ImagePreviewDialog src="/preview.png" alt="Result" onClose={vi.fn()} />);
    expect(screen.getByRole("img", { name: "Result" })).toBeTruthy();
  });

  it("requests close when Escape is pressed", () => {
    const onClose = vi.fn();
    render(<ImagePreviewDialog src="/preview.png" onClose={onClose} />);

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
