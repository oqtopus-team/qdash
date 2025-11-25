"use client";

import { InteractiveFigureContent } from "./InteractiveFigureContent";

interface InteractiveFigureModalProps {
  isOpen: boolean;
  onClose: () => void;
  figureJsonPath: string;
  title?: string;
  figureIndex?: number;
  totalFigures?: number;
  onNavigatePrevious?: () => void;
  onNavigateNext?: () => void;
}

export function InteractiveFigureModal({
  isOpen,
  onClose,
  figureJsonPath,
  title = "Interactive Figure",
  figureIndex,
  totalFigures,
  onNavigatePrevious,
  onNavigateNext,
}: InteractiveFigureModalProps) {
  if (!isOpen) return null;

  const displayTitle =
    figureIndex !== undefined ? `${title} ${figureIndex + 1}` : title;

  return (
    <dialog className="modal modal-open">
      <div className="modal-box w-fit min-w-[500px] max-w-[95vw] h-fit max-h-[95vh] p-6">
        <div className="flex justify-between items-center mb-4">
          <h3 className="font-bold text-lg">{displayTitle}</h3>
          <button onClick={onClose} className="btn btn-sm btn-circle btn-ghost">
            ✕
          </button>
        </div>

        <InteractiveFigureContent
          figureJsonPath={figureJsonPath}
          figureIndex={figureIndex}
          totalFigures={totalFigures}
          onNavigatePrevious={onNavigatePrevious}
          onNavigateNext={onNavigateNext}
        />
      </div>
      <form method="dialog" className="modal-backdrop">
        <button onClick={onClose}>close</button>
      </form>
    </dialog>
  );
}
