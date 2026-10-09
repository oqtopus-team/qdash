/**
 * Figures the user attaches to a chat message.
 *
 * The bytes go to the Copilot runtime with the turn; the browser keeps only a
 * preview for the thread. Large images are downscaled before upload: vision
 * models charge tokens per pixel patch, and a calibration plot stays legible
 * well below screen resolution.
 */

import type { ChatImageAttachment } from "@/types/copilotChat";

/** Attachments per message; the evaluation tool reads the newest figure. */
export const MAX_ATTACHMENTS = 4;
/** Longest edge after downscaling, in pixels. */
export const MAX_IMAGE_EDGE = 1600;
const ACCEPTED_IMAGE_TYPES = ["image/png", "image/jpeg"] as const;
export const ACCEPT_ATTRIBUTE = ACCEPTED_IMAGE_TYPES.join(",");

/** An attachment staged in the composer. */
export interface StagedAttachment extends ChatImageAttachment {
  /** Stable key for React lists and removal. */
  id: string;
  name: string;
  /** Data URL for the thumbnail. */
  previewUrl: string;
}

export function isSupportedImage(file: Pick<File, "type">): boolean {
  return (ACCEPTED_IMAGE_TYPES as readonly string[]).includes(file.type);
}

/** Supported images from a drop, paste, or file picker, newest-first order kept. */
export function acceptedImageFiles(files: Iterable<File> | null | undefined): File[] {
  return files ? [...files].filter(isSupportedImage) : [];
}

/** Image files carried by a paste event (screenshots arrive this way). */
export function pastedImageFiles(data: DataTransfer | null): File[] {
  if (!data) return [];
  const files: File[] = [];
  for (const item of data.items) {
    if (item.kind !== "file") continue;
    const file = item.getAsFile();
    if (file) files.push(file);
  }
  return acceptedImageFiles(files);
}

/** Room left for more attachments, so a batch is cut rather than refused. */
export function attachmentRoom(current: number): number {
  return Math.max(MAX_ATTACHMENTS - current, 0);
}

/** Target size that keeps the aspect ratio with the longest edge at most `maxEdge`. */
export function fitWithin(
  width: number,
  height: number,
  maxEdge = MAX_IMAGE_EDGE,
): { width: number; height: number } {
  const longest = Math.max(width, height);
  if (longest <= maxEdge || longest === 0) return { width, height };
  const scale = maxEdge / longest;
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
  };
}

/** The base64 payload of a data URL, without the `data:...;base64,` prefix. */
export function dataUrlToBase64(dataUrl: string): { data: string; mimeType: string } {
  const match = /^data:([^;,]+);base64,(.*)$/s.exec(dataUrl);
  if (!match) throw new Error("not a base64 data URL");
  return { mimeType: match[1], data: match[2] };
}

function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error ?? new Error("could not read file"));
    reader.readAsDataURL(file);
  });
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => resolve(image);
    image.onerror = () => reject(new Error("could not decode image"));
    image.src = src;
  });
}

/**
 * Stage one file: decode it, downscale if needed, and keep a preview.
 * JPEG stays JPEG; everything else is re-encoded as PNG so plots keep crisp lines.
 */
export async function stageAttachment(file: File): Promise<StagedAttachment> {
  const original = await readAsDataUrl(file);
  const image = await loadImage(original);
  const { width, height } = fitWithin(image.naturalWidth, image.naturalHeight);
  let dataUrl = original;
  if (width !== image.naturalWidth || height !== image.naturalHeight) {
    const canvas = document.createElement("canvas");
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext("2d");
    if (!context) throw new Error("canvas is not available");
    context.drawImage(image, 0, 0, width, height);
    dataUrl =
      file.type === "image/jpeg"
        ? canvas.toDataURL("image/jpeg", 0.9)
        : canvas.toDataURL("image/png");
  }
  const { data, mimeType } = dataUrlToBase64(dataUrl);
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    name: file.name,
    previewUrl: dataUrl,
    data,
    mimeType,
  };
}
