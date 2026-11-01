type PlotlyTrace = Record<string, unknown>;

export type FigureAnalysis = {
  path: string;
  taskId?: string;
  traceCount: number;
  summaries: string[];
  warnings: string[];
};

function numericArray(value: unknown): number[] {
  return Array.isArray(value) ? value.filter((item): item is number => typeof item === "number" && Number.isFinite(item)) : [];
}

function numericMatrix(value: unknown): number[][] {
  return Array.isArray(value)
    ? value.map((row) => numericArray(row)).filter((row) => row.length > 0)
    : [];
}

function matrixValue(matrix: number[][], row: number, column: number): number | undefined {
  return matrix[row]?.[column];
}

function formatNumber(value: number): string {
  const abs = Math.abs(value);
  if (abs >= 1000 || (abs > 0 && abs < 0.001)) return value.toExponential(2);
  if (abs >= 100) return value.toFixed(1);
  if (abs >= 10) return value.toFixed(3);
  return value.toFixed(5).replace(/0+$/, "").replace(/\.$/, "");
}

function formatMaybeNumber(value: number | undefined): string {
  return typeof value === "number" && Number.isFinite(value) ? formatNumber(value) : "n/a";
}

function compactStats(values: number[]): string {
  if (!values.length) return "no numeric values";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const mean = values.reduce((sum, value) => sum + value, 0) / values.length;
  return `n=${values.length} min=${formatNumber(min)} max=${formatNumber(max)} mean=${formatNumber(mean)}`;
}

function boxed(title: string, body: string[]): string[] {
  const rawLines = [` ${title} `, ...body];
  const width = Math.min(100, Math.max(...rawLines.map((line) => line.length), title.length + 4));
  const top = `╭${` ${title} `.padEnd(width, "─")}╮`;
  const bottom = `╰${"─".repeat(width)}╯`;
  const middle = body.map((line) => `│ ${line.padEnd(width - 2)} │`);
  return [top, ...middle, bottom];
}

export function analyzePlotlyFigure(path: string, figure: unknown, taskId?: string): FigureAnalysis {
  const object = figure && typeof figure === "object" ? figure as Record<string, unknown> : {};
  const traces = Array.isArray(object.data) ? object.data.filter((trace): trace is PlotlyTrace => Boolean(trace) && typeof trace === "object") : [];
  const summaries: string[] = [];
  const warnings: string[] = [];

  traces.forEach((trace, index) => {
    const type = typeof trace.type === "string" ? trace.type : "unknown";
    const name = typeof trace.name === "string" ? trace.name : `trace ${index}`;
    if (type === "scatter" || Array.isArray(trace.y)) {
      const y = numericArray(trace.y);
      const x = numericArray(trace.x);
      const err = trace.error_y && typeof trace.error_y === "object" ? (trace.error_y as Record<string, unknown>).value : undefined;
      summaries.push(`${index}: scatter ${name} y(${compactStats(y)}) first=${formatMaybeNumber(y[0])} last=${formatMaybeNumber(y[y.length - 1])}${typeof err === "number" ? ` err=${formatNumber(err)}` : ""}`);
      if (y.length >= 5) {
        const tail = y.slice(Math.floor(y.length / 2));
        const tailSpan = Math.max(...tail) - Math.min(...tail);
        if (tailSpan > 0.4) warnings.push(`scatter ${name}: late repetitions still have large span ${formatNumber(tailSpan)}; repeated-pulse response may be unstable`);
        const firstStep = Math.abs((y[1] ?? y[0]) - y[0]);
        if (firstStep > 0.6 && Math.abs(y[y.length - 1]) > 0.1) warnings.push(`scatter ${name}: large first-step contrast but non-zero final offset ${formatNumber(y[y.length - 1])}`);
      }
      if (x.length && y.length && x.length !== y.length) warnings.push(`scatter ${name}: x/y length mismatch ${x.length}/${y.length}`);
      return;
    }

    if (type === "heatmap" || Array.isArray(trace.z)) {
      const z = numericMatrix(trace.z);
      const flat = z.flat();
      summaries.push(`${index}: heatmap ${z.length}x${z[0]?.length ?? 0} z(${compactStats(flat)})`);
      if (z.length === 4 && z.every((row) => row.length === 4)) {
        const diag = [0, 1, 2, 3].map((i) => z[i][i]);
        const pop10 = diag[2];
        const coh0011Re = matrixValue(z, 0, 3);
        summaries.push(`   4x4 diag=[${diag.map(formatNumber).join(", ")}]  z00,11=${formatMaybeNumber(coh0011Re)}`);
        if (pop10 > 0.15) warnings.push(`4x4 heatmap: |10> population/component is high (${formatNumber(pop10)}); suspect Bell/Zx angle, phase, or cancel error`);
      }
      return;
    }

    summaries.push(`${index}: ${type}`);
  });

  if (!traces.length) warnings.push("no Plotly data traces found");
  return { path, taskId, traceCount: traces.length, summaries, warnings };
}

export function figureAnalysisText(analysis: FigureAnalysis): string {
  return boxed("QDash Figure Analysis", [
    `path ${analysis.path}`,
    ...(analysis.taskId ? [`task ${analysis.taskId}`] : []),
    `traces ${analysis.traceCount}`,
    "",
    "Summaries",
    ...analysis.summaries.map((line) => `  - ${line}`),
    "",
    "Warnings",
    ...(analysis.warnings.length ? analysis.warnings.map((line) => `  - ${line}`) : ["  - none"]),
  ]).join("\n");
}
