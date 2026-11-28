import { type ReactNode, useId } from "react";

import type { Visibility } from "@/components/ui/VisibilityLabel";

interface VisibilitySelectorProps {
  value: Visibility;
  onChange: (visibility: Visibility) => void;
  /** What "Private" means for this record. */
  privateDescription: ReactNode;
  /** What sharing with the project means for this record. */
  projectDescription: ReactNode;
  privateLabel?: string;
  projectLabel?: string;
  legend?: string;
  /** Help text under the choices. */
  hint?: ReactNode;
  disabled?: boolean;
}

function Choice({
  name,
  checked,
  label,
  description,
  disabled,
  onSelect,
}: {
  name: string;
  checked: boolean;
  label: string;
  description: ReactNode;
  disabled: boolean;
  onSelect: () => void;
}) {
  return (
    <label className="choice-field gap-3 rounded-[var(--radius-field)] border border-base-300 p-3">
      <input
        type="radio"
        name={name}
        className="radio radio-sm"
        checked={checked}
        disabled={disabled}
        onChange={onSelect}
      />
      <span>
        <span className="block font-medium">{label}</span>
        <span className="block text-xs text-base-content/60">{description}</span>
      </span>
    </label>
  );
}

/** Choose whether a record is private to its owner or shared with the project. */
export function VisibilitySelector({
  value,
  onChange,
  privateDescription,
  projectDescription,
  privateLabel = "Private",
  projectLabel = "Shared with project",
  legend = "Sharing",
  hint,
  disabled = false,
}: VisibilitySelectorProps) {
  const name = `${useId()}-visibility`;
  return (
    <fieldset className="fieldset" disabled={disabled}>
      <legend className="fieldset-legend">{legend}</legend>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <Choice
          name={name}
          checked={value === "private"}
          label={privateLabel}
          description={privateDescription}
          disabled={disabled}
          onSelect={() => onChange("private")}
        />
        <Choice
          name={name}
          checked={value === "project"}
          label={projectLabel}
          description={projectDescription}
          disabled={disabled}
          onSelect={() => onChange("project")}
        />
      </div>
      {hint && <p className="label whitespace-normal">{hint}</p>}
    </fieldset>
  );
}
