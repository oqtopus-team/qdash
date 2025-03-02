declare module "react-plotly.js" {
  import { Component } from "react";
  import { PlotParams } from "plotly.js";

  export interface PlotlyComponentProps extends Partial<PlotParams> {
    data: Array<Partial<Plotly.PlotData>>;
    layout?: Partial<Plotly.Layout>;
    config?: Partial<Plotly.Config>;
    frames?: Plotly.Frame[];
    style?: React.CSSProperties;
    useResizeHandler?: boolean;
    debug?: boolean;
    onInitialized?: (figure: Plotly.Figure, graphDiv: HTMLElement) => void;
    onUpdate?: (figure: Plotly.Figure, graphDiv: HTMLElement) => void;
    onPurge?: (figure: Plotly.Figure, graphDiv: HTMLElement) => void;
    onError?: (err: Error) => void;
    onSelected?: (event: Plotly.PlotSelectionEvent) => void;
    onClick?: (event: Plotly.PlotMouseEvent) => void;
    onHover?: (event: Plotly.PlotHoverEvent) => void;
    onUnhover?: (event: Plotly.PlotHoverEvent) => void;
    onRelayout?: (event: Plotly.PlotRelayoutEvent) => void;
  }

  export default class Plot extends Component<PlotlyComponentProps> {}
}
