import type { StylesConfig, GroupBase } from "react-select";

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
      backgroundColor: "oklch(var(--b1))",
      borderColor: state.isFocused
        ? "oklch(var(--p))"
        : "oklch(var(--bc) / 0.2)",
      borderRadius: "var(--rounded-btn, 0.5rem)",
      minHeight: "2.5rem",
      height: "2.5rem",
      boxShadow: state.isFocused ? "0 0 0 2px oklch(var(--p) / 0.2)" : "none",
      "&:hover": {
        borderColor: "oklch(var(--bc) / 0.4)",
      },
    }),
    valueContainer: (provided) => ({
      ...provided,
      padding: "0 0.75rem",
      height: "2.5rem",
    }),
    input: (provided) => ({
      ...provided,
      margin: 0,
      padding: 0,
      color: "oklch(var(--bc))",
    }),
    singleValue: (provided) => ({
      ...provided,
      color: "oklch(var(--bc))",
    }),
    placeholder: (provided) => ({
      ...provided,
      color: "oklch(var(--bc) / 0.5)",
    }),
    indicatorsContainer: (provided) => ({
      ...provided,
      height: "2.5rem",
    }),
    dropdownIndicator: (provided) => ({
      ...provided,
      padding: "0 0.5rem",
      color: "oklch(var(--bc) / 0.5)",
      "&:hover": {
        color: "oklch(var(--bc))",
      },
    }),
    clearIndicator: (provided) => ({
      ...provided,
      padding: "0 0.25rem",
      color: "oklch(var(--bc) / 0.5)",
      "&:hover": {
        color: "oklch(var(--er))",
      },
    }),
    indicatorSeparator: () => ({
      display: "none",
    }),
    menu: (provided) => ({
      ...provided,
      backgroundColor: "oklch(var(--b1))",
      borderRadius: "var(--rounded-box, 0.5rem)",
      border: "1px solid oklch(var(--bc) / 0.2)",
      boxShadow:
        "0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)",
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
        ? "oklch(var(--p))"
        : state.isFocused
          ? "oklch(var(--b2))"
          : "transparent",
      color: state.isSelected ? "oklch(var(--pc))" : "oklch(var(--bc))",
      borderRadius: "var(--rounded-btn, 0.375rem)",
      padding: "0.5rem 0.75rem",
      cursor: "pointer",
      "&:active": {
        backgroundColor: state.isSelected
          ? "oklch(var(--p))"
          : "oklch(var(--b3))",
      },
    }),
    group: (provided) => ({
      ...provided,
      paddingTop: "0.5rem",
    }),
    groupHeading: (provided) => ({
      ...provided,
      color: "oklch(var(--bc) / 0.6)",
      fontSize: "0.75rem",
      fontWeight: 600,
      textTransform: "uppercase",
      letterSpacing: "0.05em",
      padding: "0.25rem 0.75rem",
      marginBottom: "0.25rem",
    }),
    noOptionsMessage: (provided) => ({
      ...provided,
      color: "oklch(var(--bc) / 0.5)",
      padding: "0.75rem",
    }),
    loadingMessage: (provided) => ({
      ...provided,
      color: "oklch(var(--bc) / 0.5)",
    }),
    multiValue: (provided) => ({
      ...provided,
      backgroundColor: "oklch(var(--b2))",
      borderRadius: "var(--rounded-badge, 1rem)",
    }),
    multiValueLabel: (provided) => ({
      ...provided,
      color: "oklch(var(--bc))",
      padding: "0.125rem 0.5rem",
    }),
    multiValueRemove: (provided) => ({
      ...provided,
      color: "oklch(var(--bc) / 0.5)",
      borderRadius: "0 var(--rounded-badge, 1rem) var(--rounded-badge, 1rem) 0",
      "&:hover": {
        backgroundColor: "oklch(var(--er) / 0.2)",
        color: "oklch(var(--er))",
      },
    }),
  };
}

/**
 * Smaller variant for compact layouts
 */
export function getDaisySelectStylesSm<
  Option,
  IsMulti extends boolean = false,
  Group extends GroupBase<Option> = GroupBase<Option>,
>(): StylesConfig<Option, IsMulti, Group> {
  return {
    control: (provided, state) => ({
      ...provided,
      backgroundColor: "oklch(var(--b1))",
      borderColor: state.isFocused
        ? "oklch(var(--p))"
        : "oklch(var(--bc) / 0.2)",
      borderRadius: "var(--rounded-btn, 0.5rem)",
      minHeight: "2rem",
      height: "2rem",
      boxShadow: state.isFocused ? "0 0 0 2px oklch(var(--p) / 0.2)" : "none",
      "&:hover": {
        borderColor: "oklch(var(--bc) / 0.4)",
      },
    }),
    valueContainer: (provided) => ({
      ...provided,
      padding: "0 0.5rem",
      height: "2rem",
    }),
    input: (provided) => ({
      ...provided,
      margin: 0,
      padding: 0,
      color: "oklch(var(--bc))",
    }),
    singleValue: (provided) => ({
      ...provided,
      color: "oklch(var(--bc))",
    }),
    placeholder: (provided) => ({
      ...provided,
      color: "oklch(var(--bc) / 0.5)",
    }),
    indicatorsContainer: (provided) => ({
      ...provided,
      height: "2rem",
    }),
    dropdownIndicator: (provided) => ({
      ...provided,
      padding: "0 0.375rem",
      color: "oklch(var(--bc) / 0.5)",
      "&:hover": {
        color: "oklch(var(--bc))",
      },
    }),
    clearIndicator: (provided) => ({
      ...provided,
      padding: "0 0.25rem",
      color: "oklch(var(--bc) / 0.5)",
      "&:hover": {
        backgroundColor: "oklch(var(--er) / 0.2)",
        color: "oklch(var(--er))",
      },
    }),
    indicatorSeparator: () => ({
      display: "none",
    }),
    menu: (provided) => ({
      ...provided,
      backgroundColor: "oklch(var(--b1))",
      borderRadius: "var(--rounded-box, 0.5rem)",
      border: "1px solid oklch(var(--bc) / 0.2)",
      boxShadow:
        "0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)",
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
        ? "oklch(var(--p))"
        : state.isFocused
          ? "oklch(var(--b2))"
          : "transparent",
      color: state.isSelected ? "oklch(var(--pc))" : "oklch(var(--bc))",
      borderRadius: "var(--rounded-btn, 0.375rem)",
      padding: "0.375rem 0.5rem",
      fontSize: "0.875rem",
      cursor: "pointer",
      "&:active": {
        backgroundColor: state.isSelected
          ? "oklch(var(--p))"
          : "oklch(var(--b3))",
      },
    }),
    group: (provided) => ({
      ...provided,
      paddingTop: "0.5rem",
    }),
    groupHeading: (provided) => ({
      ...provided,
      color: "oklch(var(--bc) / 0.6)",
      fontSize: "0.625rem",
      fontWeight: 600,
      textTransform: "uppercase",
      letterSpacing: "0.05em",
      padding: "0.25rem 0.5rem",
      marginBottom: "0.125rem",
    }),
    noOptionsMessage: (provided) => ({
      ...provided,
      color: "oklch(var(--bc) / 0.5)",
      padding: "0.5rem",
      fontSize: "0.875rem",
    }),
    loadingMessage: (provided) => ({
      ...provided,
      color: "oklch(var(--bc) / 0.5)",
    }),
    multiValue: (provided) => ({
      ...provided,
      backgroundColor: "oklch(var(--b2))",
      borderRadius: "var(--rounded-badge, 1rem)",
    }),
    multiValueLabel: (provided) => ({
      ...provided,
      color: "oklch(var(--bc))",
      padding: "0.125rem 0.375rem",
      fontSize: "0.75rem",
    }),
    multiValueRemove: (provided) => ({
      ...provided,
      color: "oklch(var(--bc) / 0.5)",
      borderRadius: "0 var(--rounded-badge, 1rem) var(--rounded-badge, 1rem) 0",
      "&:hover": {
        backgroundColor: "oklch(var(--er) / 0.2)",
        color: "oklch(var(--er))",
      },
    }),
  };
}
