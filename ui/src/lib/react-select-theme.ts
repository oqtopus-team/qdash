import type { StylesConfig, GroupBase } from "react-select";

/**
 * Height of a DaisyUI field at the default (`md`) size: the same formula DaisyUI uses
 * for `input`, `select`, and `btn`, so a React-Select control lines up with them in a row.
 */
export const SELECT_CONTROL_HEIGHT = "calc(var(--size-field, 0.25rem) * 10)";

const baseContent = (percent: number) =>
  `color-mix(in oklch, var(--color-base-content) ${percent}%, transparent)`;

/**
 * DaisyUI-compatible theme for React-Select
 * Provides consistent styling that matches the DaisyUI design system
 */
export function getDaisySelectStyles<
  Option,
  IsMulti extends boolean = false,
  Group extends GroupBase<Option> = GroupBase<Option>,
>(): StylesConfig<Option, IsMulti, Group> {
  return {
    control: (provided, state) => ({
      ...provided,
      backgroundColor: "var(--color-base-100)",
      borderColor: state.isFocused ? "var(--color-primary)" : "var(--color-base-300)",
      borderRadius: "0.5rem",
      minHeight: SELECT_CONTROL_HEIGHT,
      // A multi-select grows with its chips; a single select keeps the field height.
      height: state.isMulti ? "auto" : SELECT_CONTROL_HEIGHT,
      boxShadow: "none",
      "&:hover": {
        borderColor: baseContent(25),
      },
    }),
    valueContainer: (provided, state) => ({
      ...provided,
      padding: state.isMulti ? "0.125rem 0.75rem" : "0 0.75rem",
    }),
    input: (provided) => ({
      ...provided,
      margin: 0,
      padding: 0,
      color: "var(--color-base-content)",
    }),
    singleValue: (provided) => ({
      ...provided,
      color: "var(--color-base-content)",
    }),
    placeholder: (provided) => ({
      ...provided,
      color: baseContent(50),
    }),
    indicatorsContainer: (provided) => ({
      ...provided,
      alignSelf: "stretch",
    }),
    dropdownIndicator: (provided) => ({
      ...provided,
      padding: "0 0.5rem",
      color: baseContent(50),
      "&:hover": {
        color: "var(--color-base-content)",
      },
    }),
    clearIndicator: (provided) => ({
      ...provided,
      padding: "0 0.25rem",
      color: baseContent(50),
      "&:hover": {
        color: "var(--color-error)",
      },
    }),
    indicatorSeparator: () => ({
      display: "none",
    }),
    menu: (provided) => ({
      ...provided,
      backgroundColor: "var(--color-base-100)",
      borderRadius: "0.5rem",
      border: `1px solid ${baseContent(20)}`,
      boxShadow: "0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)",
      zIndex: 50,
      overflow: "hidden",
    }),
    menuList: (provided) => ({
      ...provided,
      padding: "0.25rem",
    }),
    option: (provided, state) => ({
      ...provided,
      backgroundColor: state.isSelected
        ? "var(--color-primary)"
        : state.isFocused
          ? "var(--color-base-200)"
          : "transparent",
      color: state.isSelected ? "var(--color-primary-content)" : "var(--color-base-content)",
      borderRadius: "0.375rem",
      padding: "0.5rem 0.75rem",
      cursor: "pointer",
      "&:active": {
        backgroundColor: state.isSelected ? "var(--color-primary)" : "var(--color-base-300)",
      },
    }),
    group: (provided) => ({
      ...provided,
      paddingTop: "0.5rem",
    }),
    groupHeading: (provided) => ({
      ...provided,
      color: baseContent(60),
      fontSize: "0.75rem",
      fontWeight: 500,
      textTransform: "none",
      padding: "0.25rem 0.75rem",
      marginBottom: "0.25rem",
    }),
    noOptionsMessage: (provided) => ({
      ...provided,
      color: baseContent(50),
      padding: "0.75rem",
    }),
    loadingMessage: (provided) => ({
      ...provided,
      color: baseContent(50),
    }),
    multiValue: (provided) => ({
      ...provided,
      backgroundColor: "var(--color-base-200)",
      borderRadius: "1rem",
    }),
    multiValueLabel: (provided) => ({
      ...provided,
      color: "var(--color-base-content)",
      padding: "0.125rem 0.5rem",
    }),
    multiValueRemove: (provided) => ({
      ...provided,
      color: baseContent(50),
      borderRadius: "0 1rem 1rem 0",
      "&:hover": {
        backgroundColor: "color-mix(in oklch, var(--color-error) 20%, transparent)",
        color: "var(--color-error)",
      },
    }),
  };
}
