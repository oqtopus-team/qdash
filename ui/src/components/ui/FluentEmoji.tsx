"use client";

import { useState } from "react";
import Image from "next/image";

/**
 * Fluent Emoji - Microsoft's 3D emoji set
 * CDN: https://github.com/microsoft/fluentui-emoji
 */

// Mapping of simple names to Fluent Emoji asset paths
const EMOJI_MAP: Record<string, string> = {
  // Status
  check: "Check%20mark%20button/3D/check_mark_button_3d.png",
  success: "Check%20mark%20button/3D/check_mark_button_3d.png",
  error: "Cross%20mark/3D/cross_mark_3d.png",
  cross: "Cross%20mark/3D/cross_mark_3d.png",
  warning: "Warning/3D/warning_3d.png",
  info: "Information/3D/information_3d.png",

  // Actions & UI
  prohibited: "Prohibited/3D/prohibited_3d.png",
  "no-entry": "No%20entry/3D/no_entry_3d.png",
  sparkles: "Sparkles/3D/sparkles_3d.png",
  party: "Party%20popper/3D/party_popper_3d.png",
  lightbulb: "Light%20bulb/3D/light_bulb_3d.png",
  rocket: "Rocket/3D/rocket_3d.png",
  fire: "Fire/3D/fire_3d.png",

  // Data & Charts
  chart: "Bar%20chart/3D/bar_chart_3d.png",
  "chart-bar": "Bar%20chart/3D/bar_chart_3d.png",
  "chart-up": "Chart%20increasing/3D/chart_increasing_3d.png",
  "chart-down": "Chart%20decreasing/3D/chart_decreasing_3d.png",

  // Objects
  gear: "Gear/3D/gear_3d.png",
  wrench: "Wrench/3D/wrench_3d.png",
  "magnifying-glass": "Magnifying%20glass%20tilted%20left/3D/magnifying_glass_tilted_left_3d.png",
  folder: "File%20folder/3D/file_folder_3d.png",
  file: "Page%20facing%20up/3D/page_facing_up_3d.png",

  // Science & Tech
  brain: "Brain/3D/brain_3d.png",
  atom: "Atom%20symbol/3D/atom_symbol_3d.png",
  microchip: "Desktop%20computer/3D/desktop_computer_3d.png",
  computer: "Desktop%20computer/3D/desktop_computer_3d.png",
  "test-tube": "Test%20tube/3D/test_tube_3d.png",
  dna: "Dna/3D/dna_3d.png",

  // Misc
  clock: "Alarm%20clock/3D/alarm_clock_3d.png",
  hourglass: "Hourglass%20not%20done/3D/hourglass_not_done_3d.png",
  empty: "Empty%20nest/3D/empty_nest_3d.png",
  target: "Bullseye/3D/bullseye_3d.png",

  // Medals & Trophies
  "medal-gold": "1st%20place%20medal/3D/1st_place_medal_3d.png",
  "medal-silver": "2nd%20place%20medal/3D/2nd_place_medal_3d.png",
  "medal-bronze": "3rd%20place%20medal/3D/3rd_place_medal_3d.png",
  trophy: "Trophy/3D/trophy_3d.png",

  // Communication
  "speech-balloon": "Speech%20balloon/3D/speech_balloon_3d.png",

  // Arrows & Controls
  "left-right": "Left-right%20arrow/3D/left-right_arrow_3d.png",
  compress: "Collision/3D/collision_3d.png",

  // Avatar - Animals
  fox: "/avatars/fox.png",
  cat: "/avatars/cat.png",
  dog: "/avatars/dog.png",
  rabbit: "/avatars/rabbit.png",
  bear: "/avatars/bear.png",
  panda: "/avatars/panda.png",
  koala: "/avatars/koala.png",
  tiger: "/avatars/tiger.png",
  lion: "/avatars/lion.png",
  unicorn: "/avatars/unicorn.png",
  owl: "/avatars/owl.png",
  octopus: "/avatars/octopus.png",
  butterfly: "/avatars/butterfly.png",
  dolphin: "/avatars/dolphin.png",
  whale: "/avatars/whale.png",
  penguin: "/avatars/penguin.png",

  // Avatar - Nature & Objects
  sun: "/avatars/sun.png",
  moon: "/avatars/moon.png",
  star: "/avatars/star.png",
  rainbow: "/avatars/rainbow.png",
  cloud: "/avatars/cloud.png",
  snowflake: "/avatars/snowflake.png",
  cherry: "/avatars/cherry.png",
  tulip: "/avatars/tulip.png",
  sunflower: "/avatars/sunflower.png",
  mushroom: "/avatars/mushroom.png",
  crystal: "/avatars/crystal.png",
  planet: "/avatars/planet.png",
};

// Avatar emoji keys for random selection
const AVATAR_EMOJIS = [
  "fox",
  "cat",
  "dog",
  "rabbit",
  "bear",
  "panda",
  "koala",
  "tiger",
  "lion",
  "unicorn",
  "owl",
  "octopus",
  "butterfly",
  "dolphin",
  "whale",
  "penguin",
  "sun",
  "moon",
  "star",
  "rainbow",
  "cloud",
  "snowflake",
  "cherry",
  "tulip",
  "sunflower",
  "mushroom",
  "crystal",
  "planet",
];

/**
 * Generate a consistent emoji key from a username
 */
export function getAvatarEmoji(username: string): string {
  if (!username) return "star";
  // Simple hash function to get consistent index
  let hash = 0;
  for (let i = 0; i < username.length; i++) {
    const char = username.charCodeAt(i);
    hash = (hash << 5) - hash + char;
    hash = hash & hash; // Convert to 32bit integer
  }
  const index = Math.abs(hash) % AVATAR_EMOJIS.length;
  return AVATAR_EMOJIS[index];
}

const CDN_BASE = "https://raw.githubusercontent.com/microsoft/fluentui-emoji/main/assets";

interface FluentEmojiProps {
  /** Emoji name from EMOJI_MAP or direct asset path */
  name: keyof typeof EMOJI_MAP | string;
  /** Size in pixels (default: 24) */
  size?: number;
  /** Additional CSS classes */
  className?: string;
  /** Alt text for accessibility */
  alt?: string;
}

function emojiAssetSrc(name: keyof typeof EMOJI_MAP | string): string {
  const assetPath = EMOJI_MAP[name] || name;
  if (
    assetPath.startsWith("/") ||
    assetPath.startsWith("http://") ||
    assetPath.startsWith("https://")
  ) {
    return assetPath;
  }
  return CDN_BASE + "/" + assetPath;
}

export function FluentEmoji({ name, size = 24, className = "", alt }: FluentEmojiProps) {
  const [hasImageError, setHasImageError] = useState(false);
  const src = emojiAssetSrc(name);

  if (hasImageError) {
    return (
      <span
        aria-label={alt || name}
        className={
          "inline-flex items-center justify-center rounded-full bg-base-300 text-base-content/70 " +
          className
        }
        role="img"
        style={{ width: size, height: size, fontSize: Math.max(10, Math.round(size * 0.5)) }}
      >
        {(alt || name).slice(0, 1).toUpperCase()}
      </span>
    );
  }

  return (
    <Image
      src={src}
      alt={alt || name}
      width={size}
      height={size}
      className={"inline-block " + className}
      onError={() => setHasImageError(true)}
      unoptimized
    />
  );
}
