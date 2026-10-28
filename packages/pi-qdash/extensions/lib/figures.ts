import type { Theme } from "@earendil-works/pi-coding-agent";
import { Image, truncateToWidth } from "@earendil-works/pi-tui";
import type { QDashClient } from "@oqtopus-team/qdash-client";

export type FigureDetails = {
  tool: string;
  path: string;
  mediaType: string;
  sizeBytes: number;
  base64?: string;
  text?: string;
  taskId?: string;
  figurePaths?: string[];
  jsonFigurePaths?: string[];
};

export function mediaTypeForPath(path: string): string {
  const lower = path.toLowerCase();
  if (lower.endsWith(".png")) return "image/png";
  if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return "image/jpeg";
  if (lower.endsWith(".gif")) return "image/gif";
  if (lower.endsWith(".webp")) return "image/webp";
  if (lower.endsWith(".json")) return "application/json";
  return "application/octet-stream";
}

export async function fetchFigureDetails(client: QDashClient, path: string): Promise<FigureDetails> {
  const file = await client.getExecutionFigure(path);
  const bytes = Buffer.from(file.data);
  const mediaType = file.mediaType || mediaTypeForPath(path);
  const details: FigureDetails = {
    tool: "qdash_get_figure",
    path,
    mediaType,
    sizeBytes: bytes.byteLength,
  };
  if (mediaType.startsWith("image/")) details.base64 = bytes.toString("base64");
  else details.text = bytes.toString("utf8");
  return details;
}

function boxed(title: string, body: string[]): string[] {
  const rawLines = [` ${title} `, ...body];
  const width = Math.min(100, Math.max(...rawLines.map((line) => line.length), title.length + 4));
  const top = `╭${` ${title} `.padEnd(width, "─")}╮`;
  const bottom = `╰${"─".repeat(width)}╯`;
  const middle = body.map((line) => `│ ${line.padEnd(width - 2)} │`);
  return [top, ...middle, bottom];
}

export function figureResultText(details: FigureDetails): string {
  const lines = boxed("QDash Figure", [
    `path ${details.path}`,
    `type ${details.mediaType}`,
    `size ${details.sizeBytes} bytes`,
    ...(details.taskId ? [`task ${details.taskId}`] : []),
    ...(details.figurePaths?.length ? [`figures ${details.figurePaths.length}`] : []),
    ...(details.jsonFigurePaths?.length ? [`json figures ${details.jsonFigurePaths.length}`] : []),
    ...(details.text ? ["", ...details.text.split("\n").slice(0, 12).map((line) => `  ${line}`)] : []),
  ]);
  return lines.join("\n");
}

function textComponent(lines: string[]) {
  return {
    render(width: number) {
      return lines.map((line) => truncateToWidth(line, width));
    },
    invalidate() {},
  };
}

export function figureComponent(details: FigureDetails, theme: Theme) {
  if (details.base64 && details.mediaType.startsWith("image/")) {
    return new Image(details.base64, details.mediaType, { fallbackColor: (text: string) => theme.fg("dim", text) }, { maxWidthCells: 90, maxHeightCells: 30 });
  }
  return textComponent(figureResultText(details).split("\n"));
}
