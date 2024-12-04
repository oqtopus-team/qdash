import React from "react";

import { createComponent } from "@lit/react";
import { ColorLegendElement } from "color-legend-element";

/** wraps the ColorLegendElement in a React Component */
export const ColorLegendComponent = createComponent({
  tagName: "color-legend",
  elementClass: ColorLegendElement,
  react: React,
  // NOTE: ColorLegendElement currently has no events
  // events: {
  //   onactivate: "activate",
  //   onchange: "change",
  // },
});
