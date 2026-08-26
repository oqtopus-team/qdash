// Theme definitions - single source of truth
// Keep synchronized with the DaisyUI theme imports and custom themes in globals.css.

export const AVAILABLE_THEMES = [
  "light",
  "dark",
  "cupcake",
  "emerald",
  "corporate",
  "synthwave",
  "nord",
  "night",
  "dracula",
  "dim",
  "abyss",
  "business",
  "coffee",
  "sunset",
] as const;

export type ThemeName = (typeof AVAILABLE_THEMES)[number];

export const DARK_THEMES: ThemeName[] = [
  "dark",
  "synthwave",
  "night",
  "dracula",
  "business",
  "coffee",
  "dim",
  "sunset",
  "abyss",
];
