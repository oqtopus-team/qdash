"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";

import {
  getListForumLabelsQueryKey,
  getListForumPostsQueryKey,
  useCreateForumLabel,
  useDeleteForumLabel,
  useUpdateForumLabel,
} from "@/client/forum/forum";

import { NEUTRAL_FORUM_LABEL_COLOR, type ForumLabelDefinition } from "./categories";
import { ForumLabelBadge } from "./ForumLabelBadge";

type ForumLabelManagerProps = {
  labels: ForumLabelDefinition[];
};

export function ForumLabelManager({ labels }: ForumLabelManagerProps) {
  const queryClient = useQueryClient();
  const [labelKey, setLabelKey] = useState("");
  const [labelName, setLabelName] = useState("");
  const [labelDescription, setLabelDescription] = useState("");
  const [labelColor, setLabelColor] = useState(NEUTRAL_FORUM_LABEL_COLOR);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editName, setEditName] = useState("");
  const [editDescription, setEditDescription] = useState("");
  const [editColor, setEditColor] = useState(NEUTRAL_FORUM_LABEL_COLOR);

  const createMutation = useCreateForumLabel();
  const updateMutation = useUpdateForumLabel();
  const deleteMutation = useDeleteForumLabel();

  const invalidateLabels = () => {
    queryClient.invalidateQueries({ queryKey: getListForumLabelsQueryKey() });
    queryClient.invalidateQueries({ queryKey: getListForumPostsQueryKey() });
  };

  const submitLabel = async () => {
    const trimmedName = labelName.trim();
    if (!trimmedName) return;
    await createMutation.mutateAsync({
      data: {
        key: labelKey.trim() || null,
        name: trimmedName,
        description: labelDescription.trim() || undefined,
        color: labelColor,
      },
    });
    setLabelKey("");
    setLabelName("");
    setLabelDescription("");
    setLabelColor(NEUTRAL_FORUM_LABEL_COLOR);
    invalidateLabels();
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
  };

  const removeLabel = (label: ForumLabelDefinition) => {
    if (label.isSystem) return;
    deleteMutation.mutate({ labelKey: label.id }, { onSuccess: () => invalidateLabels() });
  };

  return (
    <div className="card bg-base-200 shadow-lg mb-4">
      <div className="card-body">
        <div className="flex items-center justify-between gap-3">
          <h2 className="card-title text-sm">Forum Labels</h2>
          <span className="text-xs text-base-content/50">
            System labels are managed automatically and cannot be deleted.
          </span>
        </div>
        <div className="mb-4 grid gap-2 sm:grid-cols-[130px_150px_1fr_72px_80px]">
          <input
            className="input input-bordered input-sm"
            value={labelKey}
            onChange={(event) => setLabelKey(event.target.value)}
            placeholder="key (optional)"
          />
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
          <input
            type="color"
            className="input input-bordered input-sm h-9 w-full p-1"
            value={labelColor}
            onChange={(event) => setLabelColor(event.target.value)}
            aria-label="Label color"
          />
          <button
            className="btn btn-primary btn-sm"
            onClick={submitLabel}
            disabled={!labelName.trim() || createMutation.isPending}
          >
            Add
          </button>
        </div>
        <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
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
                      <input
                        type="color"
                        className="input input-bordered input-xs h-7 w-10 p-0.5"
                        value={editColor}
                        onChange={(event) => setEditColor(event.target.value)}
                        aria-label="Label color"
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
                    <button
                      type="button"
                      className="min-w-0 flex-1 text-left"
                      onClick={() => startEdit(item)}
                      title="Edit label"
                    >
                      <div className="flex items-center gap-2">
                        <ForumLabelBadge label={item} />
                        {item.isSystem && (
                          <span className="badge badge-ghost badge-xs">system</span>
                        )}
                      </div>
                      {item.description && (
                        <p className="mt-1 truncate text-xs text-base-content/50">
                          {item.description}
                        </p>
                      )}
                    </button>
                    <button
                      className="btn btn-ghost btn-xs text-error"
                      onClick={() => removeLabel(item)}
                      disabled={item.isSystem || deleteMutation.isPending}
                      title={item.isSystem ? "System labels cannot be deleted" : "Delete label"}
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
