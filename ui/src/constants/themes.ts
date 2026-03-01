// Theme definitions - single source of truth
// Keep synchronized with @import statements in globals.css (lines 546-547, 686-692)

export const AVAILABLE_THEMES = [
  "light",
  "dark",
  "night",
  "dracula",
  "dim",
  "abyss",
  "business",
  "coffee",
  "sunset",
] as const;

export type ThemeName = (typeof AVAILABLE_THEMES)[number];

export const DEV_THEMES: ThemeName[] = ["light", "dark"];

export const DARK_THEMES: ThemeName[] = [
  "dark",
  "night",
  "dracula",
  "business",
  "coffee",
  "dim",
  "sunset",
  "abyss",
];
