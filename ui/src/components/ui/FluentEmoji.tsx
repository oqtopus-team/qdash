"use client";

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
  "chart-up": "Chart%20increasing/3D/chart_increasing_3d.png",
  "chart-down": "Chart%20decreasing/3D/chart_decreasing_3d.png",

  // Objects
  gear: "Gear/3D/gear_3d.png",
  wrench: "Wrench/3D/wrench_3d.png",
  "magnifying-glass":
    "Magnifying%20glass%20tilted%20left/3D/magnifying_glass_tilted_left_3d.png",
  folder: "File%20folder/3D/file_folder_3d.png",
  file: "Page%20facing%20up/3D/page_facing_up_3d.png",

  // Science & Tech
  atom: "Atom%20symbol/3D/atom_symbol_3d.png",
  "test-tube": "Test%20tube/3D/test_tube_3d.png",
  dna: "Dna/3D/dna_3d.png",

  // Misc
  clock: "Alarm%20clock/3D/alarm_clock_3d.png",
  hourglass: "Hourglass%20not%20done/3D/hourglass_not_done_3d.png",
  empty: "Empty%20nest/3D/empty_nest_3d.png",
};

const CDN_BASE =
  "https://raw.githubusercontent.com/microsoft/fluentui-emoji/main/assets";

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

export function FluentEmoji({
  name,
  size = 24,
  className = "",
  alt,
}: FluentEmojiProps) {
  const assetPath = EMOJI_MAP[name] || name;
  const src = `${CDN_BASE}/${assetPath}`;

  return (
    <Image
      src={src}
      alt={alt || name}
      width={size}
      height={size}
      className={`inline-block ${className}`}
      unoptimized // CDN images don't need Next.js optimization
    />
  );
}

// Export available emoji names for reference
export const FLUENT_EMOJI_NAMES = Object.keys(EMOJI_MAP);
