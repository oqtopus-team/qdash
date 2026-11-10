"use client";

import Image from "next/image";

import { useCustomAvatarSpec } from "@/lib/avatar/avatarSpecs";
import { glyphAvatarDataUri, resolveAvatarSpec } from "@/lib/avatar/glyphAvatar";

/**
 * A glyph avatar rendered locally from a spec, shown as a `data:` URI image.
 *
 * No request is made for the image; the markup comes from the bundled glyph-avatar package and
 * `<img>` never runs script inside it.
 */
export function GlyphAvatarImage({
  spec,
  alt,
  size = 28,
  className = "",
  title,
}: {
  spec: string;
  alt: string;
  size?: number;
  className?: string;
  title?: string;
}) {
  return (
    <span className={`avatar shrink-0 ${className}`} title={title}>
      <span className="rounded-full" style={{ width: size, height: size }}>
        <Image src={glyphAvatarDataUri(spec)} alt={alt} width={size} height={size} unoptimized />
      </span>
    </span>
  );
}

/**
 * A user's glyph avatar.
 *
 * It renders at once from the username, so loading, network, and API failures still show the
 * user's automatic avatar. A custom avatar chosen on this instance replaces it when its spec
 * arrives from the batched lookup.
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
  const customSpec = useCustomAvatarSpec(username);

  if (!username) {
    return (
      <span className={`avatar avatar-placeholder shrink-0 ${className}`}>
        <span
          className="rounded-full bg-base-300 text-base-content/70"
          style={{ width: size, height: size, fontSize: Math.max(10, Math.round(size * 0.42)) }}
          role="img"
          aria-label="User avatar"
        >
          <span aria-hidden="true">?</span>
        </span>
      </span>
    );
  }

  return (
    <GlyphAvatarImage
      spec={resolveAvatarSpec(username, customSpec)}
      alt={username}
      size={size}
      className={className}
      title={username}
    />
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
