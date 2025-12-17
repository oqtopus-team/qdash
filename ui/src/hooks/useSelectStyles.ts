import { useMemo } from "react";

import type { StylesConfig, GroupBase } from "react-select";
import { getDaisySelectStyles } from "@/lib/reactSelectTheme";

interface UseSelectStylesOptions {
  labels: string[];
  placeholder: string;
  charWidth?: number;
  padding?: number;
}

/**
 * Hook that provides DaisyUI-compatible React-Select styles with dynamic width calculation
 */
export function useSelectStyles<
  T,
  IsMulti extends boolean = false,
  Group extends GroupBase<T> = GroupBase<T>,
>({
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

  const styles = useMemo<StylesConfig<T, IsMulti, Group>>(() => {
    const baseStyles = getDaisySelectStyles<T, IsMulti, Group>();

    return {
      ...baseStyles,
      container: (provided) => ({
        ...provided,
        minWidth,
      }),
      menu: (provided, state) => ({
        ...(baseStyles.menu?.(provided, state) || provided),
        minWidth,
      }),
    };
  }, [minWidth]);

  return { minWidth, styles };
}
