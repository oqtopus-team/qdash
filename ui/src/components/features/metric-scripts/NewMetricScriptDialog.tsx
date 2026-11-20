"use client";

import { type FormEvent, useId, useState } from "react";

import { useRouter } from "next/navigation";

import { useQueryClient } from "@tanstack/react-query";

import {
  getListMetricScriptsQueryKey,
  useCreateMetricScript,
  useListMetricScriptTemplates,
} from "@/client/metric-script/metric-script";
import type { MetricScriptCreateRequestVisibility } from "@/schemas";
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/Dialog";
import { useToast } from "@/components/ui/Toast";
import { getApiErrorMessage } from "@/lib/utils/apiError";

/** Source of a blank script: one qubit metric that reads a catalog value. */
const BLANK_SCRIPT = `from qdash_metrics import metric


@metric(title="T1", unit="us")
def t1(qid, ctx):
    # Latest T1 within the period, in microseconds.
    return ctx.data["t1"][qid].latest().to("us")
`;

interface NewScriptFormProps {
  onCancel: () => void;
  onCreated: () => void;
}

function NewScriptForm({ onCancel, onCreated }: NewScriptFormProps) {
  const id = useId();
  const router = useRouter();
  const toast = useToast();
  const queryClient = useQueryClient();
  const { data: templatesResponse, isLoading: templatesLoading } = useListMetricScriptTemplates({
    query: { staleTime: Infinity },
  });
  const templates = templatesResponse?.data?.templates ?? [];
  const createMutation = useCreateMetricScript();

  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [visibility, setVisibility] = useState<MetricScriptCreateRequestVisibility>("private");
  const [templateId, setTemplateId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const trimmedName = name.trim();

  const handleSubmit = (event: FormEvent) => {
    event.preventDefault();
    if (!trimmedName) return;
    setError(null);
    createMutation.mutate(
      {
        data: {
          name: trimmedName,
          description: description.trim(),
          visibility,
          ...(templateId ? { template_id: templateId } : { source: BLANK_SCRIPT }),
        },
      },
      {
        onSuccess: (response) => {
          void queryClient.invalidateQueries({ queryKey: getListMetricScriptsQueryKey() });
          toast.success("Script created");
          onCreated();
          router.push(`/custom-dashboards/scripts/${response.data.script_id}`);
        },
        onError: (mutationError) =>
          setError(getApiErrorMessage(mutationError, "Failed to create the script")),
      },
    );
  };

  const pending = createMutation.isPending;

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
          maxLength={120}
          placeholder="Script name"
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
          placeholder="What the script computes"
          onChange={(event) => setDescription(event.target.value)}
        />
      </fieldset>

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
              <span className="block font-medium">Blank script</span>
              <span className="block text-xs text-base-content/60">
                One qubit metric to start from
              </span>
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
                <span className="block text-xs text-base-content/60">{template.description}</span>
              </span>
            </label>
          ))}
        </div>
        {templatesLoading && <p className="label">Loading templates</p>}
      </fieldset>

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
                Members can use it on shared dashboards
              </span>
            </span>
          </label>
        </div>
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
        <button type="submit" className="btn btn-primary" disabled={pending || !trimmedName}>
          {pending && (
            <span data-icon="inline-start" className="loading loading-spinner loading-xs" />
          )}
          Create script
        </button>
      </div>
    </form>
  );
}

interface NewMetricScriptDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** Create a metric script from a template or a blank start, then open it in the editor. */
export function NewMetricScriptDialog({ open, onOpenChange }: NewMetricScriptDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogTitle>New metric script</DialogTitle>
        <DialogDescription className="mt-1 text-xs text-base-content/60">
          Scripts compute per-qubit or per-pair values for dashboard panels
        </DialogDescription>
        <NewScriptForm onCancel={() => onOpenChange(false)} onCreated={() => onOpenChange(false)} />
      </DialogContent>
    </Dialog>
  );
}
