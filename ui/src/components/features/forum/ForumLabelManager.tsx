"use client";

import { useId, useRef, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2 } from "lucide-react";
import { Controller, useForm } from "react-hook-form";
import { toast } from "sonner";
import { z } from "zod";

import {
  getListForumLabelsQueryKey,
  useCreateForumLabel,
  useDeleteForumLabel,
  useUpdateForumLabel,
} from "@/client/forum/forum";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

import {
  getForumLabelErrorMessage,
  NEUTRAL_FORUM_LABEL_COLOR,
  type ForumLabelDefinition,
} from "./categories";
import { ForumLabelBadge } from "./ForumLabelBadge";

/** Zod schema shared by the create and edit forms; limits mirror ForumLabelCreate/Update. */
const forumLabelSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(80, "Name must be 80 characters or fewer"),
  description: z.string().trim().max(200, "Description must be 200 characters or fewer"),
  color: z.string().regex(/^#[0-9a-fA-F]{6}$/, "Color must be a hex value such as #6b7280"),
});

type ForumLabelFormValues = z.infer<typeof forumLabelSchema>;

const EMPTY_LABEL_FORM: ForumLabelFormValues = {
  name: "",
  description: "",
  color: NEUTRAL_FORUM_LABEL_COLOR,
};

/** Returns the error element id for aria-describedby when the field is invalid. */
const errorId = (id: string, invalid: boolean) => (invalid ? `${id}-error` : undefined);

type FieldErrorProps = {
  id: string;
  message?: string;
};

/** Field-level validation message referenced by the input's aria-describedby. */
function FieldError({ id, message }: FieldErrorProps) {
  if (!message) return null;
  return (
    <p id={`${id}-error`} className="mt-1 text-xs text-error">
      {message}
    </p>
  );
}

type ForumLabelColorInputProps = {
  id: string;
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  invalid?: boolean;
  size?: "xs" | "sm";
  className?: string;
};

/** Color picker whose whole field is filled with the selected color. */
function ForumLabelColorInput({
  id,
  value,
  onChange,
  onBlur,
  invalid = false,
  size = "sm",
  className = "",
}: ForumLabelColorInputProps) {
  const sizeClass = size === "xs" ? "input-xs h-7" : "input-sm h-9";
  return (
    <label
      className={`input input-bordered relative overflow-hidden ${sizeClass} ${invalid ? "input-error" : ""} ${className}`}
      style={{ backgroundColor: value }}
    >
      <input
        id={id}
        type="color"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onBlur={onBlur}
        className="absolute inset-0 cursor-pointer opacity-0"
        aria-label="Label color"
        aria-invalid={invalid}
        aria-describedby={errorId(id, invalid)}
      />
    </label>
  );
}

type ForumLabelCreateFormProps = {
  onCreated: () => void;
};

/** Form for adding a new forum label. */
function ForumLabelCreateForm({ onCreated }: ForumLabelCreateFormProps) {
  const baseId = useId();
  const createMutation = useCreateForumLabel();
  const {
    register,
    control,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<ForumLabelFormValues>({
    resolver: zodResolver(forumLabelSchema),
    defaultValues: EMPTY_LABEL_FORM,
  });

  /** Creates the label, then clears the form and refreshes the label list. */
  const submit = async (values: ForumLabelFormValues) => {
    try {
      await createMutation.mutateAsync({
        data: {
          name: values.name,
          description: values.description || undefined,
          color: values.color,
        },
      });
      reset(EMPTY_LABEL_FORM);
      onCreated();
    } catch (error) {
      toast.error(getForumLabelErrorMessage(error, "Failed to create label"));
    }
  };

  const nameId = `${baseId}-name`;
  const descriptionId = `${baseId}-description`;
  const colorId = `${baseId}-color`;

  return (
    <form
      className="mb-4 grid items-start gap-2 sm:grid-cols-[150px_1fr_96px_80px]"
      onSubmit={handleSubmit(submit)}
      noValidate
      aria-label="Create label"
    >
      <div className="min-w-0">
        <label htmlFor={nameId} className="sr-only">
          Name
        </label>
        <input
          id={nameId}
          className={`input input-bordered input-sm w-full ${errors.name ? "input-error" : ""}`}
          placeholder="Name"
          aria-invalid={Boolean(errors.name)}
          aria-describedby={errorId(nameId, Boolean(errors.name))}
          {...register("name")}
        />
        <FieldError id={nameId} message={errors.name?.message} />
      </div>
      <div className="min-w-0">
        <label htmlFor={descriptionId} className="sr-only">
          Description
        </label>
        <input
          id={descriptionId}
          className={`input input-bordered input-sm w-full ${errors.description ? "input-error" : ""}`}
          placeholder="Description"
          aria-invalid={Boolean(errors.description)}
          aria-describedby={errorId(descriptionId, Boolean(errors.description))}
          {...register("description")}
        />
        <FieldError id={descriptionId} message={errors.description?.message} />
      </div>
      <div className="min-w-0">
        <Controller
          control={control}
          name="color"
          render={({ field, fieldState }) => (
            <ForumLabelColorInput
              id={colorId}
              value={field.value}
              onChange={field.onChange}
              onBlur={field.onBlur}
              invalid={Boolean(fieldState.error)}
              className="w-full"
            />
          )}
        />
        <FieldError id={colorId} message={errors.color?.message} />
      </div>
      <button
        type="submit"
        className="btn btn-primary btn-sm"
        disabled={isSubmitting || createMutation.isPending}
      >
        Add
      </button>
    </form>
  );
}

type ForumLabelEditFormProps = {
  label: ForumLabelDefinition;
  onCancel: () => void;
  onSaved: () => void;
};

/** Inline form for editing one existing forum label. */
function ForumLabelEditForm({ label, onCancel, onSaved }: ForumLabelEditFormProps) {
  const baseId = useId();
  // Scope by label so a save started before Cancel and a save from the reopened form run in order.
  const updateMutation = useUpdateForumLabel({
    mutation: { scope: { id: `forum-label-update:${label.id}` } },
  });
  const {
    register,
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<ForumLabelFormValues>({
    resolver: zodResolver(forumLabelSchema),
    // Follow refetched label values, such as an earlier save, without discarding the user's edits.
    values: {
      name: label.label,
      description: label.description,
      color: label.color,
    },
    resetOptions: { keepDirtyValues: true },
  });

  /** Saves the edited label, then closes the form and refreshes the label list. */
  const submit = async (values: ForumLabelFormValues) => {
    try {
      await updateMutation.mutateAsync({
        labelKey: label.id,
        data: {
          name: values.name,
          description: values.description,
          color: values.color,
        },
      });
      onSaved();
    } catch (error) {
      toast.error(getForumLabelErrorMessage(error, "Failed to update label"));
    }
  };

  const nameId = `${baseId}-name`;
  const descriptionId = `${baseId}-description`;
  const colorId = `${baseId}-color`;

  return (
    <form
      className="min-w-0 flex-1 space-y-1"
      onSubmit={handleSubmit(submit)}
      noValidate
      aria-label={`Edit label ${label.label}`}
    >
      <div className="flex items-center gap-2">
        <Controller
          control={control}
          name="color"
          render={({ field, fieldState }) => (
            <ForumLabelColorInput
              id={colorId}
              value={field.value}
              onChange={field.onChange}
              onBlur={field.onBlur}
              invalid={Boolean(fieldState.error)}
              size="xs"
              className="w-12"
            />
          )}
        />
        <label htmlFor={nameId} className="sr-only">
          Name
        </label>
        <input
          id={nameId}
          className={`input input-bordered input-xs min-w-0 flex-1 ${errors.name ? "input-error" : ""}`}
          placeholder="Name"
          aria-invalid={Boolean(errors.name)}
          aria-describedby={errorId(nameId, Boolean(errors.name))}
          {...register("name")}
        />
      </div>
      <FieldError id={colorId} message={errors.color?.message} />
      <FieldError id={nameId} message={errors.name?.message} />
      <label htmlFor={descriptionId} className="sr-only">
        Description
      </label>
      <input
        id={descriptionId}
        className={`input input-bordered input-xs w-full ${errors.description ? "input-error" : ""}`}
        placeholder="Description"
        aria-invalid={Boolean(errors.description)}
        aria-describedby={errorId(descriptionId, Boolean(errors.description))}
        {...register("description")}
      />
      <FieldError id={descriptionId} message={errors.description?.message} />
      <div className="flex justify-end gap-1">
        <button type="button" className="btn btn-ghost btn-xs" onClick={onCancel}>
          Cancel
        </button>
        <button
          type="submit"
          className="btn btn-primary btn-xs"
          disabled={isSubmitting || updateMutation.isPending}
        >
          Save
        </button>
      </div>
    </form>
  );
}

type ForumLabelManagerProps = {
  labels: ForumLabelDefinition[];
};

/** Editor-level CRUD panel for forum labels: create, edit, and delete. */
export function ForumLabelManager({ labels }: ForumLabelManagerProps) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState<{ key: string; session: number } | null>(null);
  const editSessionRef = useRef(0);
  const [pendingDelete, setPendingDelete] = useState<ForumLabelDefinition | null>(null);

  const deleteMutation = useDeleteForumLabel();

  /** Refresh label definitions and every cached forum post query (list, detail, replies). */
  const invalidateLabels = () => {
    queryClient.invalidateQueries({ queryKey: getListForumLabelsQueryKey() });
    queryClient.invalidateQueries({
      predicate: (query) =>
        typeof query.queryKey[0] === "string" && query.queryKey[0].startsWith("/forum/posts"),
    });
  };

  /** Opens the edit form for one label in a new edit session. */
  const startEditing = (key: string) => {
    editSessionRef.current += 1;
    setEditing({ key, session: editSessionRef.current });
  };

  /** Closes the edit form only if the given session still owns it. */
  const stopEditing = (session: number) => {
    setEditing((current) => (current?.session === session ? null : current));
  };

  /** Deletes a label after confirmation and refreshes the label list. */
  const removeLabel = (label: ForumLabelDefinition) => {
    deleteMutation.mutate(
      { labelKey: label.id },
      {
        onSuccess: () => {
          setPendingDelete(null);
          invalidateLabels();
        },
        onError: (error) => {
          setPendingDelete(null);
          toast.error(getForumLabelErrorMessage(error, "Failed to delete label"));
        },
      },
    );
  };

  return (
    <div className="card bg-base-200 shadow-sm mb-4">
      <div className="card-body">
        <div className="flex items-center justify-between gap-3">
          <h2 className="card-title">Forum Labels</h2>
        </div>
        <ForumLabelCreateForm onCreated={invalidateLabels} />
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {labels.length === 0 && (
            <div className="px-2.5 py-2 text-xs text-base-content/45">No labels yet</div>
          )}
          {labels.map((item) => {
            const session = editing?.key === item.id ? editing.session : null;
            return (
              <div
                key={item.id}
                className="flex items-center justify-between gap-2 rounded-lg border border-base-300 px-3 py-2"
              >
                {session !== null ? (
                  <ForumLabelEditForm
                    label={item}
                    onCancel={() => stopEditing(session)}
                    onSaved={() => {
                      stopEditing(session);
                      invalidateLabels();
                    }}
                  />
                ) : (
                  <>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <ForumLabelBadge label={item} />
                      </div>
                      {item.description && (
                        <p className="mt-1 truncate text-xs text-base-content/50">
                          {item.description}
                        </p>
                      )}
                    </div>
                    <div className="flex shrink-0 items-center">
                      <button
                        type="button"
                        className="btn btn-ghost btn-xs"
                        onClick={() => startEditing(item.id)}
                        title="Edit label"
                        aria-label="Edit label"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button
                        type="button"
                        className="btn btn-ghost btn-xs text-error"
                        onClick={() => setPendingDelete(item)}
                        disabled={deleteMutation.isPending}
                        title="Delete label"
                        aria-label="Delete label"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  </>
                )}
              </div>
            );
          })}
        </div>
      </div>
      <ConfirmDialog
        open={pendingDelete !== null}
        title="Delete label?"
        description={
          <>
            This will delete <strong>{pendingDelete?.label}</strong> and remove it from every
            thread. This cannot be undone.
          </>
        }
        confirmLabel="Delete"
        destructive
        pending={deleteMutation.isPending}
        onConfirm={() => {
          if (pendingDelete) removeLabel(pendingDelete);
        }}
        onOpenChange={(open) => !open && setPendingDelete(null)}
      />
    </div>
  );
}
