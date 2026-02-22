"use client";

import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-basic-dist";

// Create Plot component with lightweight plotly.js-basic-dist
// Default export needed for next/dynamic() lazy loading
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export const Plot = createPlotlyComponent(Plotly as any);
export default Plot;
