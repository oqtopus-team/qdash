"use client";

import Image from "next/image";
import { useEffect, useState } from "react";

import { useAvatarVersion } from "@/lib/avatar/avatarVersions";
import { userAvatarUrl } from "@/lib/avatar/glyphAvatar";

/**
 * A user's saved glyph avatar, loaded as an image from the API.
 *
 * The API generates and saves the automatic avatar on first request, so every user has one.
 * The browser revalidates the image with its ETag; an avatar saved in this tab refreshes at once.
 */
export function UserAvatar({
  username,
  size = 28,
  className = "",
}: {
  username: string;
  size?: number;
  className?: string;
}) {
  const version = useAvatarVersion(username);
  const src = username ? userAvatarUrl(username, version) : null;
  const [request, setRequest] = useState({ src, retries: 0, failed: false });
  const retries = request.src === src ? request.retries : 0;
  const failed = !src || (request.src === src && request.failed);
  const imageSrc = src && retries ? `${src}${src.includes("?") ? "&" : "?"}retry=${retries}` : src;

  useEffect(() => {
    if (!src || !failed || retries >= 2) return;
    const timer = window.setTimeout(
      () => setRequest({ src, retries: retries + 1, failed: false }),
      retries === 0 ? 1000 : 3000,
    );
    return () => window.clearTimeout(timer);
  }, [src, failed, retries]);
  const dimensions = { width: size, height: size };

  if (failed || !imageSrc) {
    return (
      <span className={`avatar avatar-placeholder shrink-0 ${className}`} title={username}>
        <span
          className="rounded-full bg-base-300 text-base-content/70"
          style={{ ...dimensions, fontSize: Math.max(10, Math.round(size * 0.42)) }}
          role="img"
          aria-label={username || "User avatar"}
        >
          <span aria-hidden="true">{username.charAt(0).toUpperCase() || "?"}</span>
        </span>
      </span>
    );
  }

  return (
    <span className={`avatar shrink-0 ${className}`} title={username}>
      <span className="rounded-full" style={dimensions}>
        <Image
          src={imageSrc}
          alt={username}
          width={size}
          height={size}
          unoptimized
          onError={() => setRequest({ src, retries, failed: true })}
        />
      </span>
    </span>
  );
}

export function QdashBotAvatar({
  size = 28,
  className = "",
  unframed = false,
}: {
  size?: number;
  className?: string;
  unframed?: boolean;
}) {
  return (
    <span
      className={`inline-flex shrink-0 items-center justify-center ${unframed ? "" : "rounded-full bg-base-100"} ${className}`}
      title="QDash"
    >
      <Image
        src={unframed ? "/oqtopus_logo.svg" : "/oqtopus_logo.png"}
        alt="OQTOPUS"
        width={size}
        height={size}
        className={unframed ? "" : "rounded-full"}
      />
    </span>
  );
}
