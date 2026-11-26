"use client";

import { useMemo } from "react";
import dynamic from "next/dynamic";

import { useUpdateCooldown } from "@/client/cooldown/cooldown";
import { useIsDarkTheme } from "@/contexts/ThemeContext";

import { CooldownWiringHistory } from "./CooldownWiringHistory";
import { SaveStatus, useDebouncedAutosave } from "./SaveStatus";

const WiringBlockEditor = dynamic(
  () =>
    import("./WiringBlockEditor").then((m) => ({
      default: m.WiringBlockEditor,
    })),
  { ssr: false },
);

interface CooldownWiringSectionProps {
  cooldownId: string;
  wiringInfo: string;
  wiringBlocks: Record<string, unknown>[];
  onChange: () => void;
}

/** BlockNote color scheme of the active theme. */
function useThemeScheme(): "light" | "dark" {
  return useIsDarkTheme() ? "dark" : "light";
}

export function CooldownWiringSection({
  cooldownId,
  wiringInfo,
  wiringBlocks,
  onChange,
}: CooldownWiringSectionProps) {
  const updateCooldown = useUpdateCooldown();
  const colorScheme = useThemeScheme();

  const initialBlocks = useMemo(
    () => (wiringBlocks.length > 0 ? wiringBlocks : undefined),
    [wiringBlocks],
  );

  const auto = useDebouncedAutosave<{
    blocks: Record<string, unknown>[];
    markdown: string;
  }>({
    initialBaseline: { blocks: wiringBlocks, markdown: wiringInfo },
    isEqual: (a, b) => JSON.stringify(a.blocks) === JSON.stringify(b.blocks),
    save: async (v) => {
      await updateCooldown.mutateAsync({
        cooldownId,
        data: { wiring_blocks: v.blocks, wiring_info: v.markdown },
      });
      onChange();
    },
  });

  return (
    <div className="text-xs">
      <div className="flex items-center justify-between mb-1 min-h-[1.25rem]">
        <span className="text-base-content/60 font-medium">Wiring info</span>
        <SaveStatus state={auto.state} savedAt={auto.savedAt} />
      </div>

      <div className="wiring-blocknote">
        <WiringBlockEditor
          initialBlocks={initialBlocks}
          legacyMarkdown={wiringInfo}
          editable
          colorScheme={colorScheme}
          onChange={(blocks, markdown) => auto.schedule({ blocks, markdown })}
        />
      </div>
      <div className="text-xs text-base-content/50 mt-1">
        Type <kbd className="kbd kbd-xs">/</kbd> for blocks (table, image, heading, list, toggle,
        code, …). Paste images with <kbd className="kbd kbd-xs">⌘/Ctrl+V</kbd>. Changes save
        automatically.
      </div>

      <div className="mt-3">
        <CooldownWiringHistory cooldownId={cooldownId} />
      </div>
    </div>
  );
}
