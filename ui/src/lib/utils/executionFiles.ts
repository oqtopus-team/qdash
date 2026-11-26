/** URL that serves a calibration figure (image or Plotly JSON) by its stored path. */
export function executionFigureUrl(path: string): string {
  return `/api/executions/figure?path=${encodeURIComponent(path)}`;
}

/** URL that serves any execution artifact file, such as raw data, by its stored path. */
export function executionArtifactUrl(path: string): string {
  return `/api/executions/artifact?path=${encodeURIComponent(path)}`;
}
