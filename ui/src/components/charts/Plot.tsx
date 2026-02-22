"use client";

import createPlotlyComponent from "react-plotly.js/factory";
import Plotly from "plotly.js-basic-dist";

// Create Plot component with lightweight plotly.js-basic-dist

const Plot = createPlotlyComponent(Plotly as any);

export default Plot;
