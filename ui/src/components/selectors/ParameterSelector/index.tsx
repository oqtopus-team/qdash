"use client";

import Select from "react-select";

import { useSelectStyles } from "@/hooks/useSelectStyles";

import type { SingleValue } from "react-select";

interface ParameterOption {
  value: string;
  label: string;
}

interface ParameterSelectorProps {
  parameters: string[];
  selectedParameter: string;
  onParameterSelect: (parameter: string) => void;
  disabled?: boolean;
}

export function ParameterSelector({
  parameters,
  selectedParameter,
  onParameterSelect,
  disabled = false,
}: ParameterSelectorProps) {
  const styles = useSelectStyles<ParameterOption>();
  const options: ParameterOption[] = parameters.map((param) => ({
    value: param,
    label: param,
  }));

  const handleChange = (option: SingleValue<ParameterOption>) => {
    onParameterSelect(option ? option.value : "");
  };

  return (
    <Select<ParameterOption>
      styles={styles}
      options={options}
      value={options.find((option) => option.value === selectedParameter) ?? null}
      onChange={handleChange}
      placeholder="Select parameter"
      className="text-base-content w-full"
      isDisabled={disabled}
    />
  );
}
