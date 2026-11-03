export type AttenuationEntry = {
  mux: string;
  line: "control" | "readout_send";
  totalDb: number;
  components: number[];
  panel?: string;
  hardwarePort?: string;
  qid?: string;
};

export type WiringInsights = {
  entries: AttenuationEntry[];
  control: { commonTotalDb?: number; anomalies: AttenuationEntry[]; totals: Record<string, number> };
  readoutSend: { commonTotalDb?: number; anomalies: AttenuationEntry[]; totals: Record<string, number> };
  suggestions: string[];
};

function ansi(code: string, text: string): string {
  return `\u001b[${code}m${text}\u001b[0m`;
}

function boxed(title: string, body: string[], color = false): string[] {
  const rawLines = [` ${title} `, ...body];
  const width = Math.min(100, Math.max(...rawLines.map((line) => line.replace(/\u001b\[[0-9;]*m/g, "").length), title.length + 4));
  const border = (text: string) => color ? ansi("90", text) : text;
  const top = `${border("╭")}${color ? ansi("1;36", ` ${title} `) : ` ${title} `}${border("─".repeat(Math.max(0, width - title.length - 2)))}${border("╮")}`;
  const bottom = border(`╰${"─".repeat(width)}╯`);
  const middle = body.map((line) => `│ ${line}${" ".repeat(Math.max(0, width - line.replace(/\u001b\[[0-9;]*m/g, "").length - 2))} │`);
  return [top, ...middle, bottom];
}

function markdownTableRows(markdown: string): string[][] {
  return markdown.split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("|") && line.endsWith("|"))
    .map((line) => line.slice(1, -1).split("|").map((cell) => cell.trim()))
    .filter((cells) => cells.length >= 7 && !cells.every((cell) => /^-+$/.test(cell.replace(/\s/g, ""))));
}

function expandPanelSpec(value: string): string[] {
  return value.split(/[、,]/).flatMap((part) => {
    const token = part.trim();
    if (!token) return [];
    const range = token.match(/^([A-Za-z]+)(\d+)\s*-\s*(\d+)$/);
    if (range) {
      const [, prefix, startText, endText] = range;
      const start = Number(startText);
      const end = Number(endText);
      const step = start <= end ? 1 : -1;
      const panels: string[] = [];
      for (let value = start; step > 0 ? value <= end : value >= end; value += step) panels.push(`${prefix}${value}`);
      return panels;
    }
    return [token];
  });
}

function splitPortsAndPanels(cell: string): { ports: string[]; panels: string[] } {
  const [portsText = cell, panelsText = ""] = cell.split(/\s+\/\s+/, 2);
  return {
    ports: portsText.split(/[、,]/).map((part) => part.trim()).filter(Boolean),
    panels: expandPanelSpec(panelsText),
  };
}

function attenuationNumbers(text: string): number[] {
  return [...text.matchAll(/(?:追加\s*)?(\d+(?:\.\d+)?)\s*dB/gi)].map((match) => Number(match[1])).filter(Number.isFinite);
}

function panelAttenuationTotals(cell: string): Array<{ panels?: string[]; components: number[]; totalDb: number }> {
  const parenthesized = [...cell.matchAll(/([^（）]+)（([^）]+)）/g)].map((match) => {
    const components = attenuationNumbers(match[1]);
    return { panels: expandPanelSpec(match[2]), components, totalDb: components.reduce((sum, value) => sum + value, 0) };
  }).filter((segment) => segment.components.length > 0);
  if (parenthesized.length > 0) return parenthesized;
  const components = attenuationNumbers(cell);
  return components.length > 0 ? [{ components, totalDb: components.reduce((sum, value) => sum + value, 0) }] : [];
}

function mostCommonTotal(entries: AttenuationEntry[]): number | undefined {
  const counts = new Map<number, number>();
  for (const entry of entries) counts.set(entry.totalDb, (counts.get(entry.totalDb) ?? 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0] - b[0])[0]?.[0];
}

function totalHistogram(entries: AttenuationEntry[]): Record<string, number> {
  const histogram: Record<string, number> = {};
  for (const entry of entries) histogram[String(entry.totalDb)] = (histogram[String(entry.totalDb)] ?? 0) + 1;
  return histogram;
}

export function analyzeWiringMarkdown(markdown: string | undefined): WiringInsights | undefined {
  if (!markdown) return undefined;
  const rows = markdownTableRows(markdown);
  const dataRows = rows.filter((cells) => /^\d+$/.test(cells[0]));
  const entries: AttenuationEntry[] = [];
  for (const cells of dataRows) {
    const mux = cells[0].padStart(2, "0");
    const muxNumber = Number(cells[0]);
    const control = splitPortsAndPanels(cells[1] ?? "");
    const controlSegments = panelAttenuationTotals(cells[5] ?? "");
    for (let index = 0; index < control.panels.length; index++) {
      const panel = control.panels[index];
      const segment = controlSegments.find((item) => item.panels?.includes(panel)) ?? (controlSegments.length === 1 ? controlSegments[0] : undefined);
      if (!segment) continue;
      entries.push({
        mux,
        line: "control",
        panel,
        hardwarePort: control.ports[index],
        qid: Number.isFinite(muxNumber) ? String(muxNumber * 4 + index) : undefined,
        totalDb: segment.totalDb,
        components: segment.components,
      });
    }
    const readoutSegments = panelAttenuationTotals(cells[6] ?? "");
    const readout = splitPortsAndPanels(cells[2] ?? "");
    if (readoutSegments[0]) {
      entries.push({
        mux,
        line: "readout_send",
        panel: readout.panels[0],
        hardwarePort: readout.ports[0],
        totalDb: readoutSegments[0].totalDb,
        components: readoutSegments[0].components,
      });
    }
  }
  const controlEntries = entries.filter((entry) => entry.line === "control");
  const readoutEntries = entries.filter((entry) => entry.line === "readout_send");
  const controlCommon = mostCommonTotal(controlEntries);
  const readoutCommon = mostCommonTotal(readoutEntries);
  const controlAnomalies = controlCommon === undefined ? [] : controlEntries.filter((entry) => entry.totalDb !== controlCommon);
  const readoutAnomalies = readoutCommon === undefined ? [] : readoutEntries.filter((entry) => entry.totalDb !== readoutCommon);
  const suggestions = [
    controlCommon !== undefined ? `Control の最頻総減衰量は ${controlCommon} dB です。` : undefined,
    controlAnomalies.length > 0
      ? `Control で最頻値と異なるポートが ${controlAnomalies.length} 件あります: ${controlAnomalies.map((entry) => entry.qid ? `q${entry.qid}` : `${entry.mux}/${entry.panel}`).join(", ")}`
      : controlEntries.length > 0 ? "Control の総減衰量は全ポートで揃っています。" : undefined,
    readoutCommon !== undefined ? `Readout send の最頻総減衰量は ${readoutCommon} dB です。` : undefined,
    readoutAnomalies.length > 0
      ? `Readout send で最頻値と異なる MUX が ${readoutAnomalies.length} 件あります: ${readoutAnomalies.map((entry) => `MUX${entry.mux}`).join(", ")}`
      : readoutEntries.length > 0 ? "Readout send の総減衰量は全 MUX で揃っています。" : undefined,
  ].filter((line): line is string => Boolean(line));
  return {
    entries,
    control: { commonTotalDb: controlCommon, anomalies: controlAnomalies, totals: totalHistogram(controlEntries) },
    readoutSend: { commonTotalDb: readoutCommon, anomalies: readoutAnomalies, totals: totalHistogram(readoutEntries) },
    suggestions,
  };
}

export function wiringInsightLines(insights: WiringInsights, color = false): string[] {
  const accent = (text: string) => color ? ansi("1;36", text) : text;
  const muted = (text: string) => color ? ansi("90", text) : text;
  const warning = (text: string) => color ? ansi("33", text) : text;
  const formatEntry = (entry: AttenuationEntry) => `${entry.qid ? `q${entry.qid}` : `MUX${entry.mux}`} ${muted(`MUX${entry.mux}`)} ${entry.panel ?? ""}${entry.hardwarePort ? `/${entry.hardwarePort}` : ""}: ${warning(`${entry.totalDb} dB`)} (${entry.components.join("+")})`;
  return boxed("QDash Wiring Insights", [
    ...insights.suggestions.map((line) => `• ${line}`),
    "",
    accent("Control totals"),
    `  ${Object.entries(insights.control.totals).map(([total, count]) => `${total} dB × ${count}`).join(", ") || muted("none")}`,
    ...(insights.control.anomalies.length > 0 ? ["", accent("Control anomalies"), ...insights.control.anomalies.map((entry) => `  ${formatEntry(entry)}`)] : []),
    "",
    accent("Readout send totals"),
    `  ${Object.entries(insights.readoutSend.totals).map(([total, count]) => `${total} dB × ${count}`).join(", ") || muted("none")}`,
    ...(insights.readoutSend.anomalies.length > 0 ? ["", accent("Readout send anomalies"), ...insights.readoutSend.anomalies.map((entry) => `  ${formatEntry(entry)}`)] : []),
  ], color);
}
