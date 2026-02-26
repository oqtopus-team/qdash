"use client";

import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-dist-min";

// Create Plot component with plotly.js-dist-min (includes all trace types)
// Default export needed for next/dynamic() lazy loading
// eslint-disable-next-line @typescript-eslint/no-explicit-any
const Plot = createPlotlyComponent(Plotly as any);
export default Plot;
