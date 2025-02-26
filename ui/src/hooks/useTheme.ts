import { useEffect, useState } from "react";

export function useTheme() {
  const [theme, setTheme] = useState(localStorage.getItem("theme") ?? "nord");

  const handleToggle = (e: any) => {
    if (e.target.checked) {
      setTheme("dracula");
    } else {
      setTheme("nord");
    }
  };

  useEffect(() => {
    localStorage.setItem("theme", theme!);
    const localTheme = localStorage.getItem("theme");
    document.querySelector("html")?.setAttribute("data-theme", localTheme!);
  }, [theme]);

  const isDarkMode = theme === "dracula";
  const textClass = isDarkMode ? "text-neutral" : "text-neutral-content";

  return { isDarkMode, textClass, handleToggle };
}
