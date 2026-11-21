"use client";

import { type FormEvent, useEffect, useId, useMemo, useRef, useState } from "react";

import { useListChips } from "@/client/chip/chip";
import { useListDashboardTemplates } from "@/client/dashboard/dashboard";
import type { DashboardResponseVisibility, DashboardTemplateResponse } from "@/schemas";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import { getApiErrorMessage } from "@/lib/utils/apiError";
import { sortChipsByDefaultPriority } from "@/lib/utils/chips";

export interface DashboardFormValues {
  name: string;
  description: string;
  visibility: DashboardResponseVisibility;
  chip_id: string | null;
  /** Template whose panels are copied into a new dashboard; null starts blank. */
  template_id?: string | null;
}

/** Radio value of the explicit "no template" choice. */
const BLANK = "blank";

interface DashboardFormProps {
  initial: DashboardFormValues | null;
  submitLabel: string;
  pending: boolean;
  error: string | null;
  onCancel: () => void;
  onSubmit: (values: DashboardFormValues) => void;
}

function TemplateChoice({
  name,
  value,
  checked,
  title,
  detail,
  onChange,
}: {
  name: string;
  value: string;
  checked: boolean;
  title: string;
  detail: string;
  onChange: () => void;
}) {
  return (
    <label
      className={`choice-field gap-3 rounded-[var(--radius-field)] border p-3 ${
        checked ? "border-primary/40 bg-primary/5" : "border-base-300"
      }`}
    >
      <input
        type="radio"
        name={name}
        value={value}
        className="radio radio-sm"
        checked={checked}
        onChange={onChange}
      />
      <span>
        <span className="block font-medium">{title}</span>
        <span className="block text-xs text-base-content/60">{detail}</span>
      </span>
    </label>
  );
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
  const isCreate = initial === null;

  const [name, setName] = useState(initial?.name ?? "");
  const [description, setDescription] = useState(initial?.description ?? "");
  const [visibility, setVisibility] = useState<DashboardResponseVisibility>(
    initial?.visibility ?? "private",
  );
  const [chipId, setChipId] = useState<string>(initial?.chip_id ?? "");

  const templatesQuery = useListDashboardTemplates({
    query: { enabled: isCreate, staleTime: Infinity },
  });
  const templates = useMemo<DashboardTemplateResponse[]>(
    () => templatesQuery.data?.data?.templates ?? [],
    [templatesQuery.data],
  );
  const templatesLoading = isCreate && !!templatesQuery.isLoading;
  const templatesFailed = isCreate && !!templatesQuery.isError;
  // "" until a default is chosen; the first template once they load, else the blank start.
  const [templateChoice, setTemplateChoice] = useState<string>("");
  const templateId = templateChoice === BLANK ? "" : templateChoice;
  const template = templates.find((entry) => entry.template_id === templateId);

  // The name follows the chosen template until the user types one of their own.
  const nameEdited = useRef(!isCreate);
  const applyTemplateChoice = (choice: string) => {
    setTemplateChoice(choice);
    if (nameEdited.current) return;
    const next = templates.find((entry) => entry.template_id === choice);
    setName(next?.name ?? "");
  };

  // Default to the first template once the list arrives; a failed or empty list starts blank.
  const templateDefaulted = useRef(!isCreate);
  useEffect(() => {
    if (templateDefaulted.current || templatesLoading) return;
    if (!templatesFailed && templates.length === 0 && templatesQuery.data === undefined) return;
    templateDefaulted.current = true;
    const first = templates[0]?.template_id ?? BLANK;
    setTemplateChoice(first);
    if (!nameEdited.current) setName(templates[0]?.name ?? "");
  }, [templates, templatesFailed, templatesLoading, templatesQuery.data]);

  // A new dashboard defaults to the most recently installed active chip, once.
  const chipDefaulted = useRef(initial !== null);
  useEffect(() => {
    if (chipDefaulted.current || chips.length === 0) return;
    chipDefaulted.current = true;
    setChipId(chips[0].chip_id);
  }, [chips]);

  const trimmedName = name.trim();
  const nameError = trimmedName ? null : "Enter a name";
  // Never submit a blank dashboard on the user's behalf while the templates are still unknown.
  const startUndecided = isCreate && templateChoice === "";

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (nameError || startUndecided) return;
    onSubmit({
      name: trimmedName,
      description: description.trim(),
      visibility,
      chip_id: chipId || null,
      ...(isCreate ? { template_id: templateId || null } : {}),
    });
  };

  const descriptionField = (
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
  );

  return (
    <form className="mt-3 flex min-h-0 flex-1 flex-col" onSubmit={handleSubmit} noValidate>
      {/* Fields scroll; the actions below stay in view on short screens. */}
      <div className="-mx-1 flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-1 pb-1">
        {isCreate && (
          <fieldset className="fieldset">
            <legend className="fieldset-legend">Start from</legend>
            {templatesLoading ? (
              <div
                className="grid grid-cols-1 gap-2 sm:grid-cols-2"
                aria-busy="true"
                aria-label="Loading templates"
              >
                <div className="skeleton h-16" />
                <div className="skeleton h-16" />
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                {templates.map((entry) => (
                  <TemplateChoice
                    key={entry.template_id}
                    name={`${id}-template`}
                    value={entry.template_id}
                    checked={templateChoice === entry.template_id}
                    title={entry.name}
                    detail={`${entry.description}. ${entry.panel_count} panels, ready to use on your chip.`}
                    onChange={() => applyTemplateChoice(entry.template_id)}
                  />
                ))}
                <TemplateChoice
                  name={`${id}-template`}
                  value={BLANK}
                  checked={templateChoice === BLANK}
                  title="Blank dashboard"
                  detail="Add panels yourself"
                  onChange={() => applyTemplateChoice(BLANK)}
                />
              </div>
            )}
            {templatesFailed ? (
              <div role="alert" className="alert alert-warning alert-soft mt-2 text-sm">
                <span>
                  {getApiErrorMessage(templatesQuery.error, "Templates could not be loaded")}. You
                  can start blank, or{" "}
                  <button
                    type="button"
                    className="link"
                    disabled={templatesQuery.isFetching}
                    onClick={() => void templatesQuery.refetch()}
                  >
                    try again
                  </button>
                  .
                </span>
              </div>
            ) : !templatesLoading && templates.length === 0 ? (
              <p className="label whitespace-normal">No templates are available in this project</p>
            ) : null}
          </fieldset>
        )}

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
            autoFocus={!isCreate}
            onChange={(event) => {
              nameEdited.current = event.target.value !== "";
              setName(event.target.value);
            }}
          />
          {isCreate && template && !nameEdited.current && (
            <p className="label whitespace-normal">
              Named after the template; change it if you like
            </p>
          )}
        </fieldset>

        <fieldset className="fieldset">
          <legend className="fieldset-legend">
            <label htmlFor={`${id}-chip`}>{isCreate ? "Chip" : "Default chip"}</label>
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
          <p className="label whitespace-normal">
            {chips.length === 0
              ? "No chip is registered yet; the dashboard opens on the newest chip once one exists"
              : "The chip the panels show by default; viewers can switch chips without changing it"}
          </p>
        </fieldset>

        <fieldset className="fieldset">
          <legend className="fieldset-legend">Sharing</legend>
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
          {isCreate && (
            <p className="label whitespace-normal">
              {visibility === "project"
                ? "A shared dashboard can only show scripts that are shared with the project"
                : "You can share it with the project later from the dashboard's actions menu"}
            </p>
          )}
        </fieldset>

        {isCreate ? (
          <details className="collapse collapse-arrow rounded-[var(--radius-field)] border border-base-300">
            <summary className="collapse-title min-h-0 py-2 text-sm">Add a description</summary>
            <div className="collapse-content pb-2">{descriptionField}</div>
          </details>
        ) : (
          descriptionField
        )}

        {error && (
          <div role="alert" className="alert alert-error alert-soft text-sm">
            {error}
          </div>
        )}
      </div>

      <div className="modal-action mt-3 shrink-0 border-t border-base-300 pt-3">
        <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={pending}>
          Cancel
        </button>
        <button
          type="submit"
          className="btn btn-primary"
          disabled={pending || !!nameError || startUndecided}
        >
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
      <DialogContent className="flex max-w-lg flex-col overflow-hidden p-4 sm:p-6">
        <DialogTitle>{mode === "create" ? "New dashboard" : "Dashboard settings"}</DialogTitle>
        <DialogDescription className="mt-1 text-xs text-base-content/60">
          {mode === "create"
            ? "Pick a template and a chip; you can adjust every panel afterwards"
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
