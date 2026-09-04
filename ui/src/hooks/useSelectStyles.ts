import { useMemo } from "react";

import type { StylesConfig, GroupBase } from "react-select";
import { getDaisySelectStyles } from "@/lib/react-select-theme";

/**
 * DaisyUI-compatible React-Select styles. Width is the caller's responsibility.
 */
export function useSelectStyles<
  T,
  IsMulti extends boolean = false,
  Group extends GroupBase<T> = GroupBase<T>,
>(): StylesConfig<T, IsMulti, Group> {
  return useMemo<StylesConfig<T, IsMulti, Group>>(() => {
    const baseStyles = getDaisySelectStyles<T, IsMulti, Group>();

    return {
      ...baseStyles,
      container: (provided) => ({
        ...provided,
        width: "100%",
      }),
      menu: (provided, state) => ({
        ...(baseStyles.menu?.(provided, state) || provided),
        width: "max-content",
        minWidth: "100%",
        maxWidth: "min(28rem, calc(100vw - 2rem))",
      }),
    };
  }, []);
}
