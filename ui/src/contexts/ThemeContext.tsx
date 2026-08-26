"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

import { themeChange } from "theme-change";
import { AVAILABLE_THEMES, type ThemeName } from "@/constants/themes";

type Theme = ThemeName;

interface ThemeContextProps {
  theme: Theme;
  setTheme: (theme: Theme) => void;
}

const ThemeContext = createContext<ThemeContextProps | undefined>(undefined);

function parseTheme(value: string | null | undefined): Theme | null {
  return AVAILABLE_THEMES.includes(value as Theme) ? (value as Theme) : null;
}

function getDefaultTheme(): Theme {
  return parseTheme(process.env.NEXT_PUBLIC_DEFAULT_THEME) ?? "light";
}

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(getDefaultTheme);

  useEffect(() => {
    const savedTheme = localStorage.getItem("theme");
    const initialTheme = parseTheme(savedTheme) ?? getDefaultTheme();
    if (savedTheme && savedTheme !== initialTheme) {
      localStorage.setItem("theme", initialTheme);
    }
    setThemeState(initialTheme);
    document.documentElement.setAttribute("data-theme", initialTheme);
    themeChange(false);
  }, []);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  const setTheme = useCallback((newTheme: Theme) => {
    setThemeState(newTheme);
    localStorage.setItem("theme", newTheme);
    document.documentElement.setAttribute("data-theme", newTheme);
  }, []);

  const value = useMemo(
    () => ({
      theme,
      setTheme,
    }),
    [theme, setTheme],
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error("useTheme must be used within a ThemeProvider");
  }
  return context;
}
