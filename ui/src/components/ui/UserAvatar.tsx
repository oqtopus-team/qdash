"use client";

import Image from "next/image";

import { FluentEmoji, getAvatarEmoji } from "@/components/ui/FluentEmoji";

type AvatarPreset = {
  key: string;
  label: string;
};

export const AVATAR_PRESETS: AvatarPreset[] = [
  { key: "fox", label: "Fox" },
  { key: "cat", label: "Cat" },
  { key: "dog", label: "Dog" },
  { key: "rabbit", label: "Rabbit" },
  { key: "bear", label: "Bear" },
  { key: "panda", label: "Panda" },
  { key: "koala", label: "Koala" },
  { key: "tiger", label: "Tiger" },
  { key: "lion", label: "Lion" },
  { key: "unicorn", label: "Unicorn" },
  { key: "owl", label: "Owl" },
  { key: "octopus", label: "Octopus" },
  { key: "butterfly", label: "Butterfly" },
  { key: "dolphin", label: "Dolphin" },
  { key: "whale", label: "Whale" },
  { key: "penguin", label: "Penguin" },
  { key: "sun", label: "Sun" },
  { key: "moon", label: "Moon" },
  { key: "star", label: "Star" },
  { key: "rainbow", label: "Rainbow" },
  { key: "cloud", label: "Cloud" },
  { key: "snowflake", label: "Snowflake" },
  { key: "cherry", label: "Cherry" },
  { key: "tulip", label: "Tulip" },
  { key: "sunflower", label: "Sunflower" },
  { key: "mushroom", label: "Mushroom" },
  { key: "crystal", label: "Crystal" },
  { key: "planet", label: "Planet" },
];

function resolveAvatarKey(username: string, avatarKey?: string | null) {
  return avatarKey || getAvatarEmoji(username);
}

export function UserAvatar({
  username,
  avatarKey,
  size = 28,
  className = "",
}: {
  username: string;
  avatarKey?: string | null;
  size?: number;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center ${className}`}
      title={username}
    >
      <FluentEmoji
        name={resolveAvatarKey(username, avatarKey)}
        size={size}
        alt={username || "User avatar"}
      />
    </span>
  );
}

export function QdashBotAvatar({
  size = 28,
  className = "",
}: {
  size?: number;
  className?: string;
}) {
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center rounded-full bg-base-100 ${className}`}
      title="QDash"
    >
      <Image
        src="/oqtopus_logo.png"
        alt="OQTOPUS"
        width={size}
        height={size}
        className="rounded-full"
      />
    </span>
  );
}
