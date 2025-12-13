import { useMemo } from "react";

import type { StylesConfig } from "react-select";

interface UseSelectStylesOptions {
  labels: string[];
  placeholder: string;
  charWidth?: number;
  padding?: number;
}

export function useSelectStyles<T>({
  labels,
  placeholder,
  charWidth = 8,
  padding = 60,
}: UseSelectStylesOptions) {
  const minWidth = useMemo(() => {
    const maxLength = Math.max(
      ...labels.map((l) => l.length),
      placeholder.length,
    );
    return maxLength * charWidth + padding;
  }, [labels, placeholder, charWidth, padding]);

  const styles = useMemo<StylesConfig<T, false>>(
    () => ({
      container: (provided) => ({
        ...provided,
        minWidth,
      }),
      control: (provided) => ({
        ...provided,
        minHeight: 38,
      }),
      menu: (provided) => ({
        ...provided,
        zIndex: 20,
        minWidth,
      }),
    }),
    [minWidth],
  );

  return { minWidth, styles };
}
