"use client";

import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { getListForumCategoriesQueryKey, useCreateForumCategory } from "@/client/forum/forum";
import { getApiErrorMessage } from "@/lib/utils/apiError";

const FORUM_CATEGORY_COLORS = [
  "neutral",
  "primary",
  "secondary",
  "accent",
  "info",
  "success",
  "warning",
  "error",
  "ghost",
] as const;

const FORUM_CATEGORY_ICONS = [
  "message-square",
  "activity",
  "network",
  "circuit-board",
  "settings",
  "calendar-check",
] as const;

// Mirrors FORUM_CATEGORY_PATTERN in src/qdash/api/schemas/forum.py.
const FORUM_CATEGORY_KEY_PATTERN = /^[a-z0-9][a-z0-9_-]*$/;

const forumCategorySchema = z.object({
  key: z
    .string()
    .trim()
    .min(1, "Key is required")
    .max(64, "Key must be 64 characters or fewer")
    .regex(FORUM_CATEGORY_KEY_PATTERN, "Use a-z, 0-9, - or _, starting with a-z or 0-9"),
  name: z.string().trim().min(1, "Name is required").max(80, "Name must be 80 characters or fewer"),
  description: z.string().trim().max(200, "Description must be 200 characters or fewer"),
  color: z.enum(FORUM_CATEGORY_COLORS),
  icon: z.enum(FORUM_CATEGORY_ICONS),
});

type ForumCategoryFormValues = z.infer<typeof forumCategorySchema>;

const DEFAULT_VALUES: ForumCategoryFormValues = {
  key: "",
  name: "",
  description: "",
  color: "neutral",
  icon: "message-square",
};

/** Inline form for creating a forum category. */
export function ForumCategoryForm() {
  const queryClient = useQueryClient();
  const createCategoryMutation = useCreateForumCategory();
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<ForumCategoryFormValues>({
    resolver: zodResolver(forumCategorySchema),
    defaultValues: DEFAULT_VALUES,
  });

  /** Creates the category, then resets the form and refreshes the list, or shows the API error. */
  const submit = async (values: ForumCategoryFormValues) => {
    setServerError(null);
    try {
      await createCategoryMutation.mutateAsync({
        data: {
          key: values.key,
          name: values.name,
          description: values.description,
          color: values.color,
          icon: values.icon,
          sort_order: null,
        },
      });
    } catch (err) {
      setServerError(getApiErrorMessage(err, "Failed to create category"));
      return;
    }
    reset(DEFAULT_VALUES);
    queryClient.invalidateQueries({ queryKey: getListForumCategoriesQueryKey() });
  };

  const isPending = isSubmitting || createCategoryMutation.isPending;

  return (
    <form className="mb-4" onSubmit={handleSubmit(submit)} noValidate>
      <div className="grid items-start gap-2 sm:grid-cols-[150px_180px_1fr_130px_160px_auto]">
        <div>
          <input
            className={`input input-bordered input-sm w-full ${errors.key ? "input-error" : ""}`}
            placeholder="key"
            aria-label="Category key"
            aria-invalid={Boolean(errors.key)}
            aria-describedby={errors.key ? "forum-category-key-error" : undefined}
            {...register("key")}
          />
          {errors.key && (
            <p id="forum-category-key-error" className="mt-1 text-xs text-error">
              {errors.key.message}
            </p>
          )}
        </div>
        <div>
          <input
            className={`input input-bordered input-sm w-full ${errors.name ? "input-error" : ""}`}
            placeholder="Name"
            aria-label="Category name"
            aria-invalid={Boolean(errors.name)}
            aria-describedby={errors.name ? "forum-category-name-error" : undefined}
            {...register("name")}
          />
          {errors.name && (
            <p id="forum-category-name-error" className="mt-1 text-xs text-error">
              {errors.name.message}
            </p>
          )}
        </div>
        <div>
          <input
            className={`input input-bordered input-sm w-full ${
              errors.description ? "input-error" : ""
            }`}
            placeholder="Description"
            aria-label="Category description"
            aria-invalid={Boolean(errors.description)}
            aria-describedby={errors.description ? "forum-category-description-error" : undefined}
            {...register("description")}
          />
          {errors.description && (
            <p id="forum-category-description-error" className="mt-1 text-xs text-error">
              {errors.description.message}
            </p>
          )}
        </div>
        <select
          className="select select-bordered select-sm w-full"
          aria-label="Category color"
          {...register("color")}
        >
          {FORUM_CATEGORY_COLORS.map((color) => (
            <option key={color} value={color}>
              {color}
            </option>
          ))}
        </select>
        <select
          className="select select-bordered select-sm w-full"
          aria-label="Category icon"
          {...register("icon")}
        >
          {FORUM_CATEGORY_ICONS.map((icon) => (
            <option key={icon} value={icon}>
              {icon}
            </option>
          ))}
        </select>
        <button type="submit" className="btn btn-primary btn-sm" disabled={isPending}>
          Add
        </button>
      </div>
      {serverError && (
        <div role="alert" className="alert alert-error mt-2 py-2 text-sm">
          {serverError}
        </div>
      )}
    </form>
  );
}
