import type { Theme } from "@earendil-works/pi-coding-agent";
import { truncateToWidth, visibleWidth } from "@earendil-works/pi-tui";

export function ansi(code: string, text: string): string {
  return `\u001b[${code}m${text}\u001b[0m`;
}

export function stripAnsi(text: string): string {
  return text.replace(/\u001b\[[0-9;]*m/g, "");
}

function displayWidth(text: string): number {
  return visibleWidth(stripAnsi(text));
}

export function padAnsi(text: string, width: number): string {
  return text + " ".repeat(Math.max(0, width - displayWidth(text)));
}

export function truncateDisplay(text: string, width: number): string {
  if (displayWidth(text) <= width) return text;
  const ellipsis = "…";
  const target = Math.max(0, width - visibleWidth(ellipsis));
  let out = "";
  let used = 0;
  for (const char of Array.from(text)) {
    const charWidth = visibleWidth(char);
    if (used + charWidth > target) break;
    out += char;
    used += charWidth;
  }
  return out + ellipsis;
}

export function boxed(title: string, body: string[], color = false): string[] {
  const plainTitle = ` ${title} `;
  const contentWidth = Math.min(
    92,
    Math.max(36, ...body.map((line) => displayWidth(line)), visibleWidth(plainTitle)),
  );
  const innerWidth = contentWidth + 2;
  const borderColor = (text: string) => color ? ansi("90", text) : text;
  const titleText = color ? ansi("1;36", plainTitle) : plainTitle;
  const top = borderColor("╭") + titleText + borderColor("─".repeat(Math.max(0, innerWidth - plainTitle.length))) + borderColor("╮");
  const bottom = borderColor("╰" + "─".repeat(innerWidth) + "╯");
  return [
    top,
    ...body.map((line) => {
      const clipped = color ? truncateToWidth(line, contentWidth) : truncateDisplay(line, contentWidth);
      return `${borderColor("│")} ${padAnsi(clipped, contentWidth)} ${borderColor("│")}`;
    }),
    bottom,
  ];
}

export function wrapPlainLine(line: string, width: number): string[] {
  if (width <= 0 || visibleWidth(line) <= width) return [line];
  const output: string[] = [];
  let rest = line;
  while (visibleWidth(rest) > width) {
    let slice = "";
    for (const char of rest) {
      if (visibleWidth(slice + char) > width) break;
      slice += char;
    }
    output.push(slice);
    rest = rest.slice(slice.length);
  }
  if (rest.length > 0) output.push(rest);
  return output;
}

export function boxLinesToWidth(title: string, body: string[], width: number, theme?: Theme): string[] {
  const contentWidth = Math.max(24, Math.min(100, width - 4));
  const border = (text: string) => theme ? theme.fg("borderMuted", text) : text;
  const titleText = ` ${title} `;
  const top = `${border("╭")}${theme ? theme.fg("accent", theme.bold(titleText)) : titleText}${border("─".repeat(Math.max(0, contentWidth + 2 - visibleWidth(titleText))))}${border("╮")}`;
  const bottom = border(`╰${"─".repeat(contentWidth + 2)}╯`);
  const rows = body.flatMap((line) => wrapPlainLine(line, contentWidth));
  return [
    top,
    ...rows.map((line) => `${border("│")} ${padAnsi(truncateDisplay(line, contentWidth), contentWidth)} ${border("│")}`),
    bottom,
  ];
}

export function textComponent(lines: string[], _theme: Theme, wrap = false) {
  return {
    render(width: number) {
      if (!wrap) return lines.map((line) => truncateToWidth(line, width));
      return lines.flatMap((line) => wrapPlainLine(line, width));
    },
    invalidate() {},
  };
}

export function formatNumber(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1000 || (abs > 0 && abs < 0.001)) return value.toExponential(2);
  if (abs >= 100) return value.toFixed(1);
  if (abs >= 10) return value.toFixed(3);
  return value.toFixed(5).replace(/0+$/, "").replace(/\.$/, "");
}

export function compactDate(value: string | undefined): string {
  if (!value) return "";
  const date = new Date(value.endsWith("Z") ? value : `${value}Z`);
  if (Number.isNaN(date.getTime())) return value.slice(0, 10);
  return `${String(date.getUTCMonth() + 1).padStart(2, "0")}/${String(date.getUTCDate()).padStart(2, "0")} ${String(date.getUTCHours()).padStart(2, "0")}:${String(date.getUTCMinutes()).padStart(2, "0")}`;
}
