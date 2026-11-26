import type { Theme } from "@earendil-works/pi-coding-agent";
import { Image } from "@earendil-works/pi-tui";
import { mediaTypeForPath, type QDashConnection } from "./qdash-connection.js";
import { plainBox, textComponent } from "./render.js";

export { mediaTypeForPath };

export type FigureDetails = {
  tool: string;
  path: string;
  mediaType: string;
  sizeBytes: number;
  base64?: string;
  text?: string;
  taskId?: string;
  /** Task name of the task result the figure belongs to, when known; evaluation hydration matches it. */
  taskName?: string;
  figurePaths?: string[];
  jsonFigurePaths?: string[];
};

export async function fetchFigureDetails(client: QDashConnection, path: string): Promise<FigureDetails> {
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

export function figureResultText(details: FigureDetails): string {
  const lines = plainBox("QDash Figure", [
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

export function figureComponent(details: FigureDetails, theme: Theme) {
  if (details.base64 && details.mediaType.startsWith("image/")) {
    return new Image(details.base64, details.mediaType, { fallbackColor: (text: string) => theme.fg("dim", text) }, { maxWidthCells: 90, maxHeightCells: 30 });
  }
  return textComponent(figureResultText(details).split("\n"), theme);
}
