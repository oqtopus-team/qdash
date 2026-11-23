import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DownloadConfirmModal } from "../DownloadConfirmModal";

afterEach(cleanup);

function renderModal(onOptionsChange = vi.fn()) {
  render(
    <DownloadConfirmModal
      isOpen
      selectedCount={2}
      options={{ figureImages: true, jsonFigures: false, rawData: false }}
      counts={{ figureImages: 4, jsonFigures: 0, rawData: 2 }}
      isSubmitting={false}
      onOptionsChange={onOptionsChange}
      onConfirm={vi.fn()}
      onClose={vi.fn()}
    />,
  );
  return onOptionsChange;
}

describe("DownloadConfirmModal options", () => {
  it("toggles an artifact type from anywhere on its row", () => {
    const onOptionsChange = renderModal();
    fireEvent.click(screen.getByText("Raw data (NetCDF)"));
    expect(onOptionsChange).toHaveBeenCalledWith({
      figureImages: true,
      jsonFigures: false,
      rawData: true,
    });
  });

  it("names each checkbox by its row and keeps it a focusable native control", () => {
    renderModal();
    const figures = screen.getByRole("checkbox", { name: /Figure images/ });
    expect(figures).toBeChecked();
    figures.focus();
    expect(figures).toHaveFocus();
  });

  it("disables a type with nothing to download, so neither the row nor the box toggles it", () => {
    const onOptionsChange = renderModal();
    const json = screen.getByRole("checkbox", { name: /JSON figures/ });
    expect(json).toBeDisabled();
    fireEvent.click(screen.getByText("JSON figures"));
    expect(onOptionsChange).not.toHaveBeenCalled();
  });
});
