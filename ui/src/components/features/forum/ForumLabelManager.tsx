"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";

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

type ForumLabelColorInputProps = {
  value: string;
  onChange: (value: string) => void;
  size?: "xs" | "sm";
  className?: string;
};

/** Color picker whose whole field is filled with the selected color. */
function ForumLabelColorInput({
  value,
  onChange,
  size = "sm",
  className = "",
}: ForumLabelColorInputProps) {
  const sizeClass = size === "xs" ? "input-xs h-7" : "input-sm h-9";
  return (
    <label
      className={`input input-bordered relative overflow-hidden ${sizeClass} ${className}`}
      style={{ backgroundColor: value }}
    >
      <input
        type="color"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="absolute inset-0 cursor-pointer opacity-0"
        aria-label="Label color"
      />
    </label>
  );
}

type ForumLabelManagerProps = {
  labels: ForumLabelDefinition[];
};

/** Editor-level CRUD panel for forum labels: create, edit, and delete. */
export function ForumLabelManager({ labels }: ForumLabelManagerProps) {
  const queryClient = useQueryClient();
  const [labelName, setLabelName] = useState("");
  const [labelDescription, setLabelDescription] = useState("");
  const [labelColor, setLabelColor] = useState(NEUTRAL_FORUM_LABEL_COLOR);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editColor, setEditColor] = useState(NEUTRAL_FORUM_LABEL_COLOR);
  const [pendingDelete, setPendingDelete] = useState<ForumLabelDefinition | null>(null);

  const createMutation = useCreateForumLabel();
  const updateMutation = useUpdateForumLabel();
  const deleteMutation = useDeleteForumLabel();

  /** Refresh label definitions and every cached forum post query (list, detail, replies). */
  const invalidateLabels = () => {
    queryClient.invalidateQueries({ queryKey: getListForumLabelsQueryKey() });
    queryClient.invalidateQueries({
      predicate: (query) =>
        typeof query.queryKey[0] === "string" && query.queryKey[0].startsWith("/forum/posts"),
    });
  };

  const submitLabel = async () => {
    const trimmedName = labelName.trim();
    if (!trimmedName) return;
    try {
      await createMutation.mutateAsync({
        data: {
          name: trimmedName,
          description: labelDescription.trim() || undefined,
          color: labelColor,
        },
      });
      setLabelName("");
      setLabelDescription("");
      setLabelColor(NEUTRAL_FORUM_LABEL_COLOR);
      invalidateLabels();
    } catch (error) {
      toast.error(getForumLabelErrorMessage(error, "Failed to create label"));
    }
  };

  const startEdit = (label: ForumLabelDefinition) => {
    setEditingKey(label.id);
    setEditName(label.label);
    setEditDescription(label.description);
    setEditColor(label.color);
  };

  const cancelEdit = () => {
    setEditingKey(null);
  };

  const saveEdit = async () => {
    if (!editingKey) return;
    const trimmedName = editName.trim();
    if (!trimmedName) return;
    try {
      await updateMutation.mutateAsync({
        labelKey: editingKey,
        data: {
          name: trimmedName,
          description: editDescription.trim(),
          color: editColor,
        },
      });
      setEditingKey(null);
      invalidateLabels();
    } catch (error) {
      toast.error(getForumLabelErrorMessage(error, "Failed to update label"));
    }
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
        <div className="mb-4 grid gap-2 sm:grid-cols-[150px_1fr_96px_80px]">
          <input
            className="input input-bordered input-sm"
            value={labelName}
            onChange={(event) => setLabelName(event.target.value)}
            placeholder="Name"
          />
          <input
            className="input input-bordered input-sm"
            value={labelDescription}
            onChange={(event) => setLabelDescription(event.target.value)}
            placeholder="Description"
          />
          <ForumLabelColorInput value={labelColor} onChange={setLabelColor} className="w-full" />
          <button
            className="btn btn-primary btn-sm"
            onClick={submitLabel}
            disabled={!labelName.trim() || createMutation.isPending}
          >
            Add
          </button>
        </div>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {labels.length === 0 && (
            <div className="px-2.5 py-2 text-xs text-base-content/45">No labels yet</div>
          )}
          {labels.map((item) => {
            const isEditing = editingKey === item.id;
            return (
              <div
                key={item.id}
                className="flex items-center justify-between gap-2 rounded-lg border border-base-300 px-3 py-2"
              >
                {isEditing ? (
                  <div className="min-w-0 flex-1 space-y-1">
                    <div className="flex items-center gap-2">
                      <ForumLabelColorInput
                        value={editColor}
                        onChange={setEditColor}
                        size="xs"
                        className="w-12"
                      />
                      <input
                        className="input input-bordered input-xs min-w-0 flex-1"
                        value={editName}
                        onChange={(event) => setEditName(event.target.value)}
                      />
                    </div>
                    <input
                      className="input input-bordered input-xs w-full"
                      value={editDescription}
                      onChange={(event) => setEditDescription(event.target.value)}
                      placeholder="Description"
                    />
                    <div className="flex justify-end gap-1">
                      <button className="btn btn-ghost btn-xs" onClick={cancelEdit}>
                        Cancel
                      </button>
                      <button
                        className="btn btn-primary btn-xs"
                        onClick={saveEdit}
                        disabled={!editName.trim() || updateMutation.isPending}
                      >
                        Save
                      </button>
                    </div>
                  </div>
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
                        onClick={() => startEdit(item)}
                        title="Edit label"
                        aria-label="Edit label"
                      >
                        <Pencil className="h-3.5 w-3.5" />
                      </button>
                      <button
                        className="btn btn-ghost btn-xs text-error"
                        onClick={() => setPendingDelete(item)}
                        disabled={deleteMutation.isPending}
                        title="Delete label"
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
