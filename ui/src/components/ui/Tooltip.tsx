"use client";

import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import type { ComponentPropsWithoutRef, ElementRef, ReactNode } from "react";
import { createContext, forwardRef, useContext } from "react";
import { twMerge } from "tailwind-merge";

type TooltipProps = ComponentPropsWithoutRef<typeof TooltipPrimitive.Root>;

const TOOLTIP_DELAY_MS = 350;
const TOOLTIP_SKIP_DELAY_MS = 150;

const SharedTooltipProviderContext = createContext(false);

/**
 * Shares the open delay across every Tooltip below it, so moving from one trigger to a
 * neighbour shows the next tooltip without waiting the full delay again.
 */
export function TooltipProvider({ children }: { children: ReactNode }) {
  return (
    <TooltipPrimitive.Provider
      delayDuration={TOOLTIP_DELAY_MS}
      skipDelayDuration={TOOLTIP_SKIP_DELAY_MS}
    >
      <SharedTooltipProviderContext.Provider value={true}>
        {children}
      </SharedTooltipProviderContext.Provider>
    </TooltipPrimitive.Provider>
  );
}

export function Tooltip(props: TooltipProps) {
  const hasSharedProvider = useContext(SharedTooltipProviderContext);
  const root = <TooltipPrimitive.Root {...props} />;
  // Outside a TooltipProvider (isolated renders, tests) the tooltip keeps its own provider.
  return hasSharedProvider ? root : <TooltipProvider>{root}</TooltipProvider>;
}

export const TooltipTrigger = TooltipPrimitive.Trigger;

export const TooltipContent = forwardRef<
  ElementRef<typeof TooltipPrimitive.Content>,
  ComponentPropsWithoutRef<typeof TooltipPrimitive.Content>
>(({ className, sideOffset = 6, collisionPadding = 12, ...props }, ref) => (
  <TooltipPrimitive.Portal>
    <TooltipPrimitive.Content
      ref={ref}
      sideOffset={sideOffset}
      collisionPadding={collisionPadding}
      className={twMerge(
        "z-[1400] max-w-72 rounded-lg border border-base-content/10 bg-base-100 px-2.5 py-1.5 text-xs text-base-content shadow-lg",
        className,
      )}
      {...props}
    />
  </TooltipPrimitive.Portal>
));
TooltipContent.displayName = TooltipPrimitive.Content.displayName;
