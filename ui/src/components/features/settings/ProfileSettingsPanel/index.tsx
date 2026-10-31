"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { getGetCurrentUserQueryKey, useUpdateCurrentUserProfile } from "@/client/auth/auth";
import { AVATAR_PRESETS, UserAvatar } from "@/components/ui/UserAvatar";
import { useAuth } from "@/contexts/AuthContext";
import { getApiErrorMessage } from "@/lib/utils/apiError";

const profileSchema = z.object({
  displayName: z
    .string()
    .trim()
    .max(100, "Display name must be 100 characters or fewer")
    .transform((value) => value || null),
  avatarKey: z
    .string()
    .max(64, "Select a valid avatar")
    .regex(/^[a-z0-9_-]*$/, "Select a valid avatar")
    .transform((value) => value || null),
});

type ProfileFormInput = z.input<typeof profileSchema>;
type ProfileFormOutput = z.output<typeof profileSchema>;

const DISPLAY_NAME_ERROR_ID = "profile-display-name-error";
const AVATAR_ERROR_ID = "profile-avatar-error";
const AVATAR_LABEL_ID = "profile-avatar-label";

/** Profile settings form for editing the current user's display name and avatar. */
export function ProfileSettingsPanel() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const [saved, setSaved] = useState(false);
  const savedTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const {
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
    formState: { errors },
  } = useForm<ProfileFormInput, unknown, ProfileFormOutput>({
    resolver: zodResolver(profileSchema),
    defaultValues: {
      displayName: user?.display_name ?? "",
      avatarKey: user?.avatar_key ?? "",
    },
  });
  const updateProfileMutation = useUpdateCurrentUserProfile({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: getGetCurrentUserQueryKey(),
        });
        setSaved(true);
        if (savedTimeoutRef.current) clearTimeout(savedTimeoutRef.current);
        savedTimeoutRef.current = setTimeout(() => setSaved(false), 2000);
      },
    },
  });

  useEffect(() => {
    reset({
      displayName: user?.display_name ?? "",
      avatarKey: user?.avatar_key ?? "",
    });
  }, [reset, user?.display_name, user?.avatar_key]);

  useEffect(
    () => () => {
      if (savedTimeoutRef.current) clearTimeout(savedTimeoutRef.current);
    },
    [],
  );

  const displayName = watch("displayName");
  const avatarKey = watch("avatarKey");
  const isDirty =
    displayName.trim() !== (user?.display_name ?? "") || avatarKey !== (user?.avatar_key ?? "");
  const displayNameError = errors.displayName?.message;
  const avatarError = errors.avatarKey?.message;

  /** Submits the normalized profile values to the API. */
  const submit = (values: ProfileFormOutput) => {
    setSaved(false);
    updateProfileMutation.mutate({
      data: { display_name: values.displayName, avatar_key: values.avatarKey },
    });
  };

  /** Selects an avatar key and marks the form dirty. */
  const selectAvatar = (key: string) => {
    setValue("avatarKey", key, { shouldDirty: true, shouldValidate: true });
  };

  return (
    <div className="card bg-base-200 shadow-lg">
      <div className="card-body">
        <h2 className="card-title mb-4">Profile</h2>
        <form onSubmit={handleSubmit(submit)} noValidate>
          <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
            <div className="flex flex-col items-center gap-3 rounded-lg bg-base-100 p-4">
              <UserAvatar username={user?.username ?? ""} avatarKey={avatarKey} size={72} />
              <div className="text-center">
                <div className="font-medium">{displayName.trim() || user?.username}</div>
                <div className="text-xs text-base-content/50">@{user?.username}</div>
              </div>
            </div>
            <div className="space-y-5">
              <div className="form-control w-full">
                <label className="label" htmlFor="profile-display-name">
                  <span className="label-text">Display name</span>
                </label>
                <input
                  id="profile-display-name"
                  className={`input input-bordered w-full ${displayNameError ? "input-error" : ""}`}
                  placeholder={user?.username ?? "Display name"}
                  aria-invalid={Boolean(displayNameError)}
                  aria-describedby={displayNameError ? DISPLAY_NAME_ERROR_ID : undefined}
                  {...register("displayName")}
                />
                {displayNameError && (
                  <p id={DISPLAY_NAME_ERROR_ID} className="mt-1 text-sm text-error">
                    {displayNameError}
                  </p>
                )}
              </div>

              <div>
                <div id={AVATAR_LABEL_ID} className="mb-2 text-sm font-medium">
                  Avatar
                </div>
                <div
                  role="group"
                  aria-labelledby={AVATAR_LABEL_ID}
                  aria-describedby={avatarError ? AVATAR_ERROR_ID : undefined}
                  className="grid grid-cols-4 gap-2 sm:grid-cols-7 md:grid-cols-9"
                >
                  <button
                    type="button"
                    className={`btn h-12 min-h-0 rounded-lg p-1 ${
                      avatarKey === "" ? "btn-primary" : "btn-ghost bg-base-100"
                    }`}
                    onClick={() => selectAvatar("")}
                    title="Automatic"
                    aria-label="Automatic"
                    aria-pressed={avatarKey === ""}
                  >
                    <UserAvatar username={user?.username ?? ""} size={28} />
                  </button>
                  {AVATAR_PRESETS.map((preset) => (
                    <button
                      key={preset.key}
                      type="button"
                      className={`btn h-12 min-h-0 rounded-lg p-1 ${
                        avatarKey === preset.key ? "btn-primary" : "btn-ghost bg-base-100"
                      }`}
                      onClick={() => selectAvatar(preset.key)}
                      title={preset.label}
                      aria-label={preset.label}
                      aria-pressed={avatarKey === preset.key}
                    >
                      <UserAvatar
                        username={user?.username ?? ""}
                        avatarKey={preset.key}
                        size={28}
                      />
                    </button>
                  ))}
                </div>
                {avatarError && (
                  <p id={AVATAR_ERROR_ID} className="mt-1 text-sm text-error">
                    {avatarError}
                  </p>
                )}
              </div>

              {updateProfileMutation.isError && (
                <div className="alert alert-error" role="alert">
                  <span>
                    {getApiErrorMessage(updateProfileMutation.error, "Failed to update profile.")}
                  </span>
                </div>
              )}
              {saved && (
                <div className="alert alert-success" role="alert">
                  <span>Profile updated.</span>
                </div>
              )}
              <button
                type="submit"
                className="btn btn-primary"
                disabled={!isDirty || updateProfileMutation.isPending}
              >
                {updateProfileMutation.isPending ? (
                  <span className="loading loading-spinner loading-xs" />
                ) : (
                  "Save Profile"
                )}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
