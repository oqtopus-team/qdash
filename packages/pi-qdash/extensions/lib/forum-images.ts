import { readFileSync, statSync } from "node:fs";
import { basename, extname, resolve } from "node:path";

const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const MAX_IMAGES_PER_REPLY = 8;
const IMAGE_TYPES: Record<string, string> = {
  ".gif": "image/gif",
  ".jpeg": "image/jpeg",
  ".jpg": "image/jpeg",
  ".png": "image/png",
  ".webp": "image/webp",
};

export type LocalForumImage = {
  path: string;
  filename: string;
  mimeType: string;
  sizeBytes: number;
  blob: Blob;
};

export type UploadedForumImage = Omit<LocalForumImage, "blob"> & { url: string };

export function loadLocalForumImages(paths: string[]): LocalForumImage[] {
  if (paths.length === 0) throw new Error("At least one image path is required");
  if (paths.length > MAX_IMAGES_PER_REPLY) {
    throw new Error(`A forum image reply supports at most ${MAX_IMAGES_PER_REPLY} images`);
  }

  const uniquePaths = [...new Set(paths.map((path) => resolve(path)))];
  if (uniquePaths.length !== paths.length) throw new Error("Duplicate image paths are not allowed");

  return uniquePaths.map((path) => {
    const mimeType = IMAGE_TYPES[extname(path).toLowerCase()];
    if (!mimeType) throw new Error(`Unsupported forum image type: ${path}`);
    const stat = statSync(path);
    if (!stat.isFile()) throw new Error(`Forum image path is not a file: ${path}`);
    if (stat.size > MAX_IMAGE_BYTES) throw new Error(`Forum image exceeds 5 MB: ${path}`);
    const bytes = readFileSync(path);
    return {
      path,
      filename: basename(path),
      mimeType,
      sizeBytes: stat.size,
      blob: new Blob([new Uint8Array(bytes)], { type: mimeType }),
    };
  });
}

export function forumImageReplyContent(
  title: string,
  images: Array<{ filename: string; url: string }>,
  interpretation: string,
): string {
  return [
    `## ${title}`,
    "",
    "分析で作成した画像を追加します。",
    "",
    ...images.flatMap((image) => [`![${image.filename}](${image.url})`, ""]),
    interpretation.trim(),
    "",
    "— 🤖 by pi-qdash",
  ].join("\n");
}

export function forumImageReplyPreview(
  title: string,
  images: Array<{ path: string; filename: string; sizeBytes: number }>,
  interpretation: string,
): string {
  return [
    `## ${title}`,
    "",
    "The following local images will be uploaded to QDash and embedded in a forum reply:",
    ...images.map((image) => `- ${image.filename} (${(image.sizeBytes / 1024).toFixed(1)} KiB) — ${image.path}`),
    "",
    interpretation.trim(),
    "",
    "— 🤖 by pi-qdash",
  ].join("\n");
}
