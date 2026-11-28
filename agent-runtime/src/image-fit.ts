import type { ImageProcessor } from "@earendil-works/pi-durable/tools";

/**
 * Maximum declared pixel count (`width * height`) allowed before Photon decodes
 * an image into an RGBA buffer (~100 MiB RGBA at 4 bytes/pixel).
 */
export const MAX_DECODED_IMAGE_PIXELS = 25_000_000;

export interface ImageDimensions {
  readonly width: number;
  readonly height: number;
}

const PNG_SIGNATURE = [0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a] as const;

function startsWithBytes(bytes: Uint8Array, prefix: readonly number[]): boolean {
  if (bytes.length < prefix.length) return false;
  return prefix.every((byte, index) => bytes[index] === byte);
}

function asciiMatches(bytes: Uint8Array, offset: number, text: string): boolean {
  if (bytes.length < offset + text.length) return false;
  for (let i = 0; i < text.length; i += 1) {
    if (bytes[offset + i] !== text.charCodeAt(i)) return false;
  }
  return true;
}

function validDimensions(width: number, height: number): ImageDimensions | undefined {
  return Number.isInteger(width) && Number.isInteger(height) && width > 0 && height > 0
    ? { width, height }
    : undefined;
}

function jpegDimensions(bytes: Uint8Array, view: DataView): ImageDimensions | undefined {
  if (bytes.length < 4 || bytes[0] !== 0xff || bytes[1] !== 0xd8) return undefined;
  let offset = 2;
  while (offset < bytes.length) {
    if (bytes[offset] !== 0xff) return undefined;
    while (offset < bytes.length && bytes[offset] === 0xff) offset += 1;
    if (offset >= bytes.length) return undefined;
    const marker = bytes[offset++]!;
    if (marker === 0x00 || marker === 0xd9 || marker === 0xda) return undefined;
    if (marker === 0x01 || (marker >= 0xd0 && marker <= 0xd8)) continue;
    if (offset + 2 > bytes.length) return undefined;
    const segmentLength = view.getUint16(offset, false);
    if (segmentLength < 2 || offset + segmentLength > bytes.length) return undefined;
    if (marker >= 0xc0 && marker <= 0xcf && marker !== 0xc4 && marker !== 0xc8 && marker !== 0xcc) {
      if (segmentLength < 7) return undefined;
      return validDimensions(view.getUint16(offset + 5, false), view.getUint16(offset + 3, false));
    }
    offset += segmentLength;
  }
  return undefined;
}

/**
 * Read declared image width and height directly from the file header without
 * decoding pixel data. Returns `undefined` for malformed or unrecognized inputs
 * so untrusted images never reach Photon's decoder unbounded.
 */
export function declaredImageDimensions(bytes: Uint8Array): ImageDimensions | undefined {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (startsWithBytes(bytes, PNG_SIGNATURE)) {
    if (bytes.length < 24 || view.getUint32(8, false) !== 13 || !asciiMatches(bytes, 12, "IHDR")) {
      return undefined;
    }
    return validDimensions(view.getUint32(16, false), view.getUint32(20, false));
  }
  if (bytes.length >= 2 && bytes[0] === 0xff && bytes[1] === 0xd8) {
    return jpegDimensions(bytes, view);
  }
  if (asciiMatches(bytes, 0, "GIF87a") || asciiMatches(bytes, 0, "GIF89a")) {
    if (bytes.length < 10) return undefined;
    return validDimensions(view.getUint16(6, true), view.getUint16(8, true));
  }
  if (asciiMatches(bytes, 0, "RIFF") && asciiMatches(bytes, 8, "WEBP")) {
    if (asciiMatches(bytes, 12, "VP8 ")) {
      if (bytes.length < 30 || bytes[23] !== 0x9d || bytes[24] !== 0x01 || bytes[25] !== 0x2a) {
        return undefined;
      }
      return validDimensions(view.getUint16(26, true) & 0x3fff, view.getUint16(28, true) & 0x3fff);
    }
    if (asciiMatches(bytes, 12, "VP8L")) {
      if (bytes.length < 25 || bytes[20] !== 0x2f) return undefined;
      const bits = view.getUint32(21, true);
      return validDimensions((bits & 0x3fff) + 1, ((bits >>> 14) & 0x3fff) + 1);
    }
    if (asciiMatches(bytes, 12, "VP8X")) {
      if (bytes.length < 30) return undefined;
      const width = bytes[24]! + (bytes[25]! << 8) + (bytes[26]! << 16) + 1;
      const height = bytes[27]! + (bytes[28]! << 8) + (bytes[29]! << 16) + 1;
      return validDimensions(width, height);
    }
    return undefined;
  }
  if (asciiMatches(bytes, 0, "BM")) {
    if (bytes.length < 26) return undefined;
    const dibHeaderSize = view.getUint32(14, true);
    if (dibHeaderSize === 12) {
      return validDimensions(view.getUint16(18, true), view.getUint16(20, true));
    }
    if (dibHeaderSize >= 40 && dibHeaderSize <= 124) {
      const rawWidth = view.getInt32(18, true);
      const rawHeight = view.getInt32(22, true);
      return rawWidth > 0 && rawHeight !== 0
        ? validDimensions(rawWidth, Math.abs(rawHeight))
        : undefined;
    }
    return undefined;
  }
  return undefined;
}

/**
 * Wrap an `ImageProcessor` so malformed headers or decompression-bomb images
 * whose declared dimensions exceed `maxPixels` are omitted before Photon decodes
 * pixels into RGBA memory.
 */
export function createBoundedImageProcessor(
  inner: ImageProcessor,
  maxPixels: number = MAX_DECODED_IMAGE_PIXELS,
): ImageProcessor {
  return {
    async prepare(bytes, mimeType, limits) {
      const dimensions = declaredImageDimensions(bytes);
      if (
        !dimensions ||
        dimensions.width > maxPixels ||
        dimensions.height > maxPixels ||
        dimensions.width * dimensions.height > maxPixels
      ) {
        return undefined;
      }
      return inner.prepare(bytes, mimeType, limits);
    },
  };
}
