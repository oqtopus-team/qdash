"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, Info } from "lucide-react";
import { useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { getGetCurrentUserQueryKey, useChangePassword } from "@/client/auth/auth";
import { useToast } from "@/components/ui/Toast";

const passwordChangeSchema = z
  .object({
    currentPassword: z.string().min(1, "Current password is required"),
    newPassword: z.string().min(4, "New password must be at least 4 characters"),
    confirmPassword: z.string().min(1, "Please confirm your new password"),
  })
  .refine((data) => data.newPassword === data.confirmPassword, {
    message: "New passwords do not match",
    path: ["confirmPassword"],
  });

type PasswordChangeFormData = z.infer<typeof passwordChangeSchema>;
type PasswordField = keyof PasswordChangeFormData;

interface PasswordInputProps {
  field: PasswordField;
  label: string;
  placeholder: string;
  visible: boolean;
  onToggleVisibility: () => void;
  register: ReturnType<typeof useForm<PasswordChangeFormData>>["register"];
  error?: string;
}

function PasswordInput({
  field,
  label,
  placeholder,
  visible,
  onToggleVisibility,
  register,
  error,
}: PasswordInputProps) {
  const errorId = `${field}-error`;

  return (
    <div className="form-control w-full">
      <label className="label" htmlFor={field}>
        <span className="label-text">{label}</span>
      </label>
      <label
        className={`input input-bordered flex w-full items-center gap-2 ${error ? "input-error" : ""}`}
      >
        <input
          id={field}
          type={visible ? "text" : "password"}
          className="grow"
          placeholder={placeholder}
          autoComplete={field === "currentPassword" ? "current-password" : "new-password"}
          aria-invalid={Boolean(error)}
          aria-describedby={error ? errorId : undefined}
          {...register(field)}
        />
        <button
          type="button"
          className="btn btn-ghost btn-xs btn-square"
          onClick={onToggleVisibility}
          aria-label={`${visible ? "Hide" : "Show"} ${label.toLowerCase()}`}
        >
          {visible ? <EyeOff size={18} aria-hidden="true" /> : <Eye size={18} aria-hidden="true" />}
        </button>
      </label>
      {error && (
        <p id={errorId} className="mt-1 text-sm text-error">
          {error}
        </p>
      )}
    </div>
  );
}

export function PasswordChangeCard() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [visibleFields, setVisibleFields] = useState<Set<PasswordField>>(new Set());
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<PasswordChangeFormData>({
    resolver: zodResolver(passwordChangeSchema),
    defaultValues: { currentPassword: "", newPassword: "", confirmPassword: "" },
  });
  const changePasswordMutation = useChangePassword({
    mutation: {
      onSuccess: () => {
        toast.success("Password changed successfully!");
        reset();
        queryClient.invalidateQueries({ queryKey: getGetCurrentUserQueryKey() });
      },
      onError: (error: unknown) => {
        const errorMessage =
          error instanceof Error
            ? error.message
            : "Failed to change password. Please check your current password.";
        toast.error(errorMessage);
      },
    },
  });

  const toggleVisibility = (field: PasswordField) => {
    setVisibleFields((current) => {
      const next = new Set(current);
      if (next.has(field)) next.delete(field);
      else next.add(field);
      return next;
    });
  };

  const submit = (data: PasswordChangeFormData) => {
    changePasswordMutation.mutate({
      data: { current_password: data.currentPassword, new_password: data.newPassword },
    });
  };

  return (
    <div className="card bg-base-200 shadow-lg">
      <div className="card-body">
        <h2 className="card-title mb-4 text-xl">Change Password</h2>
        <form onSubmit={handleSubmit(submit)} className="flex flex-col gap-4" noValidate>
          <PasswordInput
            field="currentPassword"
            label="Current Password"
            placeholder="Enter current password"
            visible={visibleFields.has("currentPassword")}
            onToggleVisibility={() => toggleVisibility("currentPassword")}
            register={register}
            error={errors.currentPassword?.message}
          />
          <PasswordInput
            field="newPassword"
            label="New Password"
            placeholder="Enter new password"
            visible={visibleFields.has("newPassword")}
            onToggleVisibility={() => toggleVisibility("newPassword")}
            register={register}
            error={errors.newPassword?.message}
          />
          <PasswordInput
            field="confirmPassword"
            label="Confirm New Password"
            placeholder="Confirm new password"
            visible={visibleFields.has("confirmPassword")}
            onToggleVisibility={() => toggleVisibility("confirmPassword")}
            register={register}
            error={errors.confirmPassword?.message}
          />

          <div className="alert alert-info mt-2">
            <Info className="h-6 w-6 shrink-0" aria-hidden="true" />
            <span className="text-sm">Password must be at least 4 characters long.</span>
          </div>

          <button
            type="submit"
            className="btn btn-primary mt-2"
            disabled={changePasswordMutation.isPending}
          >
            {changePasswordMutation.isPending ? (
              <>
                <span className="loading loading-spinner loading-sm" aria-hidden="true" />
                Changing...
              </>
            ) : (
              "Change Password"
            )}
          </button>
        </form>
      </div>
    </div>
  );
}
