"use client";

import { Dialog, DialogContent, DialogDescription, DialogTitle } from "./Dialog";

interface ImagePreviewDialogProps {
  alt?: string;
  onClose: () => void;
  src: string | null;
}

export function ImagePreviewDialog({ alt = "Preview", onClose, src }: ImagePreviewDialogProps) {
  return (
    <Dialog open={src !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-3xl p-4">
        <DialogTitle className="sr-only">Image preview</DialogTitle>
        <DialogDescription className="sr-only">
          Expanded preview of the selected image.
        </DialogDescription>
        {src && (
          // eslint-disable-next-line @next/next/no-img-element -- preview supports runtime API image URLs
          <img src={src} alt={alt} className="h-auto w-full" />
        )}
      </DialogContent>
    </Dialog>
  );
}
