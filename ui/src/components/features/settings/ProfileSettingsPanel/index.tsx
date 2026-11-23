"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { getGetCurrentUserQueryKey, useUpdateCurrentUserProfile } from "@/client/auth/auth";
import {
  getGetCurrentUserAvatarQueryKey,
  useGetCurrentUserAvatar,
  useUpdateCurrentUserAvatar,
} from "@/client/user-avatar/user-avatar";
import { GlyphAvatarPicker } from "@/components/ui/GlyphAvatarPicker";
import { GlyphAvatarImage } from "@/components/ui/UserAvatar";
import { useAuth } from "@/contexts/AuthContext";
import {
  currentAvatarSpecSession,
  setAvatarSpec,
  useCustomAvatarSpec,
} from "@/lib/avatar/avatarSpecs";
import { automaticAvatarSpec, resolveAvatarSpec } from "@/lib/avatar/glyphAvatar";
import { getApiErrorMessage } from "@/lib/utils/apiError";

const profileSchema = z.object({
  displayName: z
    .string()
    .trim()
    .max(100, "Display name must be 100 characters or fewer")
    .transform((value) => value || null),
});

type ProfileFormInput = z.input<typeof profileSchema>;
type ProfileFormOutput = z.output<typeof profileSchema>;

/** A pending avatar change: a picker spec, `null` for the automatic avatar, or none. */
type PendingAvatar = { spec: string | null } | null;

const DISPLAY_NAME_ERROR_ID = "profile-display-name-error";
const AVATAR_LABEL_ID = "profile-avatar-label";
const AVATAR_STATUS_ID = "profile-avatar-status";
const PREVIEW_SIZE = 72;

/** Profile settings form for the current user's display name and avatar. */
export function ProfileSettingsPanel() {
  const queryClient = useQueryClient();
  const { user } = useAuth();
  const username = user?.username ?? "";
  const [saved, setSaved] = useState(false);
  const [saveError, setSaveError] = useState<unknown>(null);
  const [pendingAvatar, setPendingAvatar] = useState<PendingAvatar>(null);
  // Where the picker starts after "Use automatic avatar"; otherwise it starts at the saved spec.
  const [pickerStartOverride, setPickerStartOverride] = useState<string | null>(null);
  const [pickerGeneration, setPickerGeneration] = useState(0);
  const savedTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const {
    register,
    handleSubmit,
    reset,
    watch,
    formState: { errors },
  } = useForm<ProfileFormInput, unknown, ProfileFormOutput>({
    resolver: zodResolver(profileSchema),
    defaultValues: { displayName: user?.display_name ?? "" },
  });
  const avatarQuery = useGetCurrentUserAvatar({ query: { enabled: Boolean(username) } });
  const updateProfileMutation = useUpdateCurrentUserProfile();
  const updateAvatarMutation = useUpdateCurrentUserAvatar();

  useEffect(() => {
    reset({ displayName: user?.display_name ?? "" });
  }, [reset, user?.display_name]);

  useEffect(
    () => () => {
      if (savedTimeoutRef.current) clearTimeout(savedTimeoutRef.current);
    },
    [],
  );

  const listedSpec = useCustomAvatarSpec(username);
  const savedAvatar = avatarQuery.data?.data;
  // Without the settings response, fall back to the batched lookup, then the automatic avatar.
  const savedCustomSpec = savedAvatar
    ? savedAvatar.source === "custom"
      ? savedAvatar.spec
      : null
    : listedSpec;
  const automaticSpec = username ? automaticAvatarSpec(username) : "";
  const savedSpec = username ? resolveAvatarSpec(username, savedCustomSpec) : "";
  const pickerStart = pickerStartOverride ?? savedSpec;
  const previewSpec = pendingAvatar ? (pendingAvatar.spec ?? automaticSpec) : savedSpec;
  const savedIsCustom = savedSpec !== automaticSpec;
  const isAutomatic = pendingAvatar ? pendingAvatar.spec === null : !savedIsCustom;

  const displayName = watch("displayName");
  const nameChanged = displayName.trim() !== (user?.display_name ?? "");
  const isDirty = nameChanged || pendingAvatar !== null;
  const isSaving = updateProfileMutation.isPending || updateAvatarMutation.isPending;
  const displayNameError = errors.displayName?.message;

  /** Restarts the picker at `start`, discarding its local movement and tweaks. */
  const restartPicker = (start: string | null) => {
    setPickerStartOverride(start);
    setPickerGeneration((value) => value + 1);
  };

  /** Records a picker selection; the saved avatar or the automatic one is not a custom choice. */
  const choose = (spec: string) => {
    setSaved(false);
    if (spec === savedSpec) {
      setPendingAvatar(null);
    } else if (spec === automaticSpec) {
      setPendingAvatar({ spec: null });
    } else {
      setPendingAvatar({ spec });
    }
  };

  /** Selects the automatic avatar rendered from the username. */
  const selectAutomatic = () => {
    setSaved(false);
    setPendingAvatar(savedIsCustom ? { spec: null } : null);
    restartPicker(automaticSpec);
  };

  /** Discards unsaved display name and avatar changes. */
  const discard = () => {
    reset({ displayName: user?.display_name ?? "" });
    setPendingAvatar(null);
    setSaveError(null);
    restartPicker(null);
  };

  /** Saves the changed display name and avatar. */
  const submit = async (values: ProfileFormOutput) => {
    setSaved(false);
    setSaveError(null);
    // A save that finishes after logout or a new login must not reach the new session's cache.
    const avatarSession = currentAvatarSpecSession();
    try {
      if (nameChanged) {
        await updateProfileMutation.mutateAsync({ data: { display_name: values.displayName } });
        if (avatarSession !== currentAvatarSpecSession()) return;
        await queryClient.invalidateQueries({ queryKey: getGetCurrentUserQueryKey() });
        if (avatarSession !== currentAvatarSpecSession()) return;
      }
      if (pendingAvatar) {
        const response = await updateAvatarMutation.mutateAsync({
          data: { spec: pendingAvatar.spec },
        });
        if (avatarSession !== currentAvatarSpecSession()) return;
        queryClient.setQueryData(getGetCurrentUserAvatarQueryKey(), response);
        setAvatarSpec(
          username,
          response.data.source === "custom" ? response.data.spec : null,
          avatarSession,
        );
        setPendingAvatar(null);
        restartPicker(null);
      }
      setSaved(true);
      if (savedTimeoutRef.current) clearTimeout(savedTimeoutRef.current);
      savedTimeoutRef.current = setTimeout(() => setSaved(false), 2000);
    } catch (error) {
      if (avatarSession !== currentAvatarSpecSession()) return;
      setSaveError(error);
    }
  };

  return (
    <div className="card bg-base-200 shadow-sm">
      <div className="card-body">
        <h2 className="card-title mb-4">Profile</h2>
        <form onSubmit={handleSubmit(submit)} noValidate>
          <div className="grid gap-6 lg:grid-cols-[220px_1fr]">
            <div className="flex flex-col items-center gap-3 self-start rounded-box bg-base-100 p-4">
              {username ? (
                <span data-testid={pendingAvatar ? "profile-avatar-preview" : undefined}>
                  <GlyphAvatarImage
                    spec={previewSpec}
                    alt={pendingAvatar ? "Unsaved avatar preview" : username}
                    size={PREVIEW_SIZE}
                  />
                </span>
              ) : null}
              <div className="text-center">
                <div className="font-medium">{displayName.trim() || username}</div>
                <div className="text-xs text-base-content/50">@{username}</div>
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
                  placeholder={username || "Display name"}
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

              <div className="space-y-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div id={AVATAR_LABEL_ID} className="text-sm font-medium">
                    Avatar
                  </div>
                  <button
                    type="button"
                    className="btn btn-ghost btn-sm"
                    onClick={selectAutomatic}
                    disabled={isAutomatic || !username}
                  >
                    Use automatic avatar
                  </button>
                </div>
                <p
                  id={AVATAR_STATUS_ID}
                  className="text-xs text-base-content/60"
                  aria-live="polite"
                >
                  {pendingAvatar
                    ? pendingAvatar.spec === null
                      ? "Automatic avatar selected. Save to apply it."
                      : "New avatar selected. Save to apply it."
                    : isAutomatic
                      ? "Automatic avatar generated from your username."
                      : "Custom avatar chosen on this QDash instance."}
                </p>
                {username && (
                  <GlyphAvatarPicker
                    key={`${pickerStart}:${pickerGeneration}`}
                    defaultValue={pickerStart}
                    onChange={choose}
                    labelledBy={AVATAR_LABEL_ID}
                  />
                )}
                {avatarQuery.isError && (
                  <p className="text-sm text-warning" role="status">
                    Your saved avatar settings could not be loaded. You can still choose a new one.
                  </p>
                )}
              </div>

              {saveError !== null && (
                <div className="alert alert-error" role="alert">
                  <span>{getApiErrorMessage(saveError, "Failed to update profile.")}</span>
                </div>
              )}
              {saved && (
                <div className="alert alert-success" role="alert">
                  <span>Profile updated.</span>
                </div>
              )}
              <div className="flex flex-wrap gap-2">
                <button type="submit" className="btn btn-primary" disabled={!isDirty || isSaving}>
                  {isSaving ? (
                    <span className="loading loading-spinner loading-xs" />
                  ) : (
                    "Save Profile"
                  )}
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={discard}
                  disabled={!isDirty || isSaving}
                >
                  Cancel
                </button>
              </div>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}
