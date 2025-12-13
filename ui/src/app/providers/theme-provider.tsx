"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { themeChange } from "theme-change";

type Theme = string; // Allow all daisyUI themes

interface ThemeContextProps {
  theme: Theme;
  setTheme: (theme: Theme) => void;
  isDevEnv: boolean;
}

const ThemeContext = createContext<ThemeContextProps | undefined>(undefined);

// Check if current environment is dev
function isDevEnvironment(): boolean {
  const env = process.env.NEXT_PUBLIC_ENV?.toLowerCase() ?? "";
  return env.includes("dev");
}

// Theme mapping for dev environment
const DEV_THEME_MAP: Record<string, string> = {
  light: "dev-light",
  dark: "dev-dark",
};

// Get actual theme to apply (converts based on environment)
function getActualTheme(baseTheme: string, isDev: boolean): string {
  if (isDev && DEV_THEME_MAP[baseTheme]) {
    return DEV_THEME_MAP[baseTheme];
  }
  return baseTheme;
}

// Get base theme name from dev-specific theme
function getBaseTheme(actualTheme: string): string {
  for (const [base, dev] of Object.entries(DEV_THEME_MAP)) {
    if (actualTheme === dev) {
      return base;
    }
  }
  return actualTheme;
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>("light");
  const isDevEnv = isDevEnvironment();

  useEffect(() => {
    // Get theme from localStorage on client-side only
    const savedTheme = localStorage.getItem("theme");
    if (savedTheme) {
      // Saved theme is base theme name, convert to actual theme based on env
      const baseTheme = getBaseTheme(savedTheme);
      setThemeState(baseTheme);
      const actualTheme = getActualTheme(baseTheme, isDevEnv);
      document.documentElement.setAttribute("data-theme", actualTheme);
    } else {
      // Apply default theme
      const actualTheme = getActualTheme("light", isDevEnv);
      document.documentElement.setAttribute("data-theme", actualTheme);
    }
    themeChange(false);
  }, [isDevEnv]);

  useEffect(() => {
    const actualTheme = getActualTheme(theme, isDevEnv);
    document.documentElement.setAttribute("data-theme", actualTheme);
  }, [theme, isDevEnv]);

  const setTheme = useCallback(
    (newTheme: Theme) => {
      // Save base theme name (light, dark, etc.)
      const baseTheme = getBaseTheme(newTheme);
      setThemeState(baseTheme);
      if (typeof window !== "undefined") {
        localStorage.setItem("theme", baseTheme);
        const actualTheme = getActualTheme(baseTheme, isDevEnv);
        document.documentElement.setAttribute("data-theme", actualTheme);
      }
    },
    [isDevEnv],
  );

  const value = useMemo(
    () => ({
      theme,
      setTheme,
      isDevEnv,
    }),
    [theme, setTheme, isDevEnv],
  );

  return (
    <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
  );
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return context;
}
