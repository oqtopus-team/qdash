"use client";

import { type FormEvent, useEffect, useId, useMemo, useRef, useState } from "react";

import { useListChips } from "@/client/chip/chip";
import { useListCustomDashboardTemplates } from "@/client/custom-dashboard/custom-dashboard";
import type { CustomDashboardResponseVisibility } from "@/schemas";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import { sortChipsByDefaultPriority } from "@/lib/utils/chips";

export interface DashboardFormValues {
  name: string;
  description: string;
  visibility: CustomDashboardResponseVisibility;
  chip_id: string | null;
  /** Template whose panels are copied into a new dashboard; null starts blank. */
  template_id?: string | null;
}

interface DashboardFormProps {
  initial: DashboardFormValues | null;
  submitLabel: string;
  pending: boolean;
  error: string | null;
  onCancel: () => void;
  onSubmit: (values: DashboardFormValues) => void;
}

function DashboardForm({
  initial,
  submitLabel,
  pending,
  error,
  onCancel,
  onSubmit,
}: DashboardFormProps) {
  const id = useId();
  const { data: chipsResponse } = useListChips();
  const chips = useMemo(
    () => sortChipsByDefaultPriority(chipsResponse?.data?.chips ?? []),
    [chipsResponse],
  );

  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [visibility, setVisibility] = useState<CustomDashboardResponseVisibility>(
    initial?.visibility ?? "private",
  );
  const [chipId, setChipId] = useState<string>(initial?.chip_id ?? "");
  const isCreate = initial === null;
  const { data: templatesResponse } = useListCustomDashboardTemplates({
    query: { enabled: isCreate, staleTime: Infinity },
  });
  const templates = templatesResponse?.data?.templates ?? [];
  const [templateId, setTemplateId] = useState<string>("");

  // A new dashboard defaults to the most recently installed active chip, once.
  const chipDefaulted = useRef(initial !== null);
  useEffect(() => {
    if (chipDefaulted.current || chips.length === 0) return;
    chipDefaulted.current = true;
    setChipId(chips[0].chip_id);
  }, [chips]);

  const trimmedName = name.trim();
  const nameError = trimmedName ? null : "Enter a name";

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (nameError) return;
    onSubmit({
      name: trimmedName,
      description: description.trim(),
      visibility,
      chip_id: chipId || null,
      ...(isCreate ? { template_id: templateId || null } : {}),
    });
  };

  return (
    <form className="mt-3 flex flex-col gap-3" onSubmit={handleSubmit} noValidate>
      <fieldset className="fieldset">
        <legend className="fieldset-legend">
          <label htmlFor={`${id}-name`}>Name</label>
        </legend>
        <input
          id={`${id}-name`}
          className="input w-full"
          value={name}
          maxLength={200}
          placeholder="Dashboard name"
          autoFocus
          onChange={(event) => setName(event.target.value)}
        />
      </fieldset>

      <fieldset className="fieldset">
        <legend className="fieldset-legend">
          <label htmlFor={`${id}-description`}>Description</label>
        </legend>
        <textarea
          id={`${id}-description`}
          className="textarea w-full"
          rows={2}
          value={description}
          maxLength={2000}
          placeholder="What this dashboard is for"
          onChange={(event) => setDescription(event.target.value)}
        />
      </fieldset>

      {isCreate && (
        <fieldset className="fieldset">
          <legend className="fieldset-legend">Start from</legend>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <label className="choice-field gap-3 rounded-[var(--radius-field)] border border-base-300 p-3">
              <input
                type="radio"
                name={`${id}-template`}
                className="radio radio-sm"
                checked={templateId === ""}
                onChange={() => setTemplateId("")}
              />
              <span>
                <span className="block font-medium">Blank dashboard</span>
                <span className="block text-xs text-base-content/60">Add panels yourself</span>
              </span>
            </label>
            {templates.map((template) => (
              <label
                key={template.template_id}
                className="choice-field gap-3 rounded-[var(--radius-field)] border border-base-300 p-3"
              >
                <input
                  type="radio"
                  name={`${id}-template`}
                  className="radio radio-sm"
                  checked={templateId === template.template_id}
                  onChange={() => setTemplateId(template.template_id)}
                />
                <span>
                  <span className="block font-medium">{template.name}</span>
                  <span className="block text-xs text-base-content/60">
                    {template.description}. {template.panel_count} panels, copied into your
                    dashboard.
                  </span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>
      )}

      <fieldset className="fieldset">
        <legend className="fieldset-legend">Visibility</legend>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <label className="choice-field gap-3 rounded-[var(--radius-field)] border border-base-300 p-3">
            <input
              type="radio"
              name={`${id}-visibility`}
              className="radio radio-sm"
              checked={visibility === "private"}
              onChange={() => setVisibility("private")}
            />
            <span>
              <span className="block font-medium">Private</span>
              <span className="block text-xs text-base-content/60">Only you can open it</span>
            </span>
          </label>
          <label className="choice-field gap-3 rounded-[var(--radius-field)] border border-base-300 p-3">
            <input
              type="radio"
              name={`${id}-visibility`}
              className="radio radio-sm"
              checked={visibility === "project"}
              onChange={() => setVisibility("project")}
            />
            <span>
              <span className="block font-medium">Shared with project</span>
              <span className="block text-xs text-base-content/60">
                Every project member can open it
              </span>
            </span>
          </label>
        </div>
      </fieldset>

      <fieldset className="fieldset">
        <legend className="fieldset-legend">
          <label htmlFor={`${id}-chip`}>Default chip</label>
        </legend>
        <select
          id={`${id}-chip`}
          className="select w-full"
          value={chipId}
          onChange={(event) => {
            chipDefaulted.current = true;
            setChipId(event.target.value);
          }}
        >
          <option value="">Newest chip when opened</option>
          {chips.map((chip) => (
            <option key={chip.chip_id} value={chip.chip_id}>
              {chip.chip_id}
              {chip.activity_status === "inactive" ? " (inactive)" : ""}
            </option>
          ))}
        </select>
        <p className="label whitespace-normal">Viewers can switch chips without changing this</p>
      </fieldset>

      {error && (
        <div role="alert" className="alert alert-error alert-soft text-sm">
          {error}
        </div>
      )}

      <div className="modal-action mt-2">
        <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={pending}>
          Cancel
        </button>
        <button type="submit" className="btn btn-primary" disabled={pending || !!nameError}>
          {pending && (
            <span data-icon="inline-start" className="loading loading-spinner loading-xs" />
          )}
          {submitLabel}
        </button>
      </div>
    </form>
  );
}

interface DashboardFormDialogProps {
  open: boolean;
  mode: "create" | "edit";
  initial?: DashboardFormValues;
  pending: boolean;
  error: string | null;
  onOpenChange: (open: boolean) => void;
  onSubmit: (values: DashboardFormValues) => void;
}

/** Create a dashboard, or edit its name, description, visibility and default chip. */
export function DashboardFormDialog({
  open,
  mode,
  initial,
  pending,
  error,
  onOpenChange,
  onSubmit,
}: DashboardFormDialogProps) {
  return (
    <Dialog open={open} onOpenChange={(next) => !pending && onOpenChange(next)}>
      <DialogContent className="max-w-lg">
        <DialogTitle>{mode === "create" ? "New dashboard" : "Dashboard settings"}</DialogTitle>
        <DialogDescription className="mt-1 text-xs text-base-content/60">
          {mode === "create"
            ? "Start blank or copy a template, then adjust the panels at any time"
            : "These settings are saved immediately"}
        </DialogDescription>
        <DashboardForm
          initial={initial ?? null}
          submitLabel={mode === "create" ? "Create dashboard" : "Save settings"}
          pending={pending}
          error={error}
          onCancel={() => onOpenChange(false)}
          onSubmit={onSubmit}
        />
      </DialogContent>
    </Dialog>
  );
}
