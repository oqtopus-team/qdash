/**
 * Shared BlockNote `uploadFile` handler that inlines a file as a base64 data URL.
 *
 * Used for non-image blocks (video / audio / file) in the forum editor, and for
 * every block (including images) in the cool-down editor. Keeping the bytes
 * inside the document — instead of a separate server URL — means the whole
 * document must stay well under Mongo's 16 MiB ceiling, so each file is capped
 * at 5 MB *encoded* (≈ 3.7 MB raw).
 */
const MAX_INLINE_FILE_BYTES = 5 * 1024 * 1024;

/**
 * Size in bytes of the base64 data URL {@link fileToDataUrl} produces for `file`.
 *
 * base64 expands 3 raw bytes into 4 characters, plus the `data:<mime>;base64,`
 * prefix. This is what actually gets stored in Mongo, so the cap is enforced
 * against the encoded size rather than the raw `File.size`.
 */
function encodedDataUrlBytes(file: File): number {
  const prefix = `data:${file.type || "application/octet-stream"};base64,`;
  return prefix.length + 4 * Math.ceil(file.size / 3);
}

function fileToDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(reader.error ?? new Error("read failed"));
    reader.onload = () => resolve(reader.result as string);
    reader.readAsDataURL(file);
  });
}

/**
 * Validate and inline any file (image, video, audio, …) as a base64 data URL.
 * Rejects files larger than {@link MAX_INLINE_FILE_BYTES}.
 */
export async function uploadInlineFile(file: File): Promise<string> {
  const encodedBytes = encodedDataUrlBytes(file);
  if (encodedBytes > MAX_INLINE_FILE_BYTES) {
    throw new Error(
      `File is too large (${(encodedBytes / 1024 / 1024).toFixed(1)} MB encoded). Max 5 MB.`,
    );
  }
  return fileToDataUrl(file);
}
