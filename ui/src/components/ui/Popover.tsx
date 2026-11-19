"use client";

import * as PopoverPrimitive from "@radix-ui/react-popover";
import type { ComponentPropsWithoutRef, ElementRef } from "react";
import { forwardRef } from "react";
import { twMerge } from "tailwind-merge";

export const Popover = PopoverPrimitive.Root;

/**
 * Positions the popover against an element. Pass `virtualRef` to anchor it to a node that
 * React does not render, such as a link inside rendered Markdown.
 */
export const PopoverAnchor = PopoverPrimitive.Anchor;

export const PopoverContent = forwardRef<
  ElementRef<typeof PopoverPrimitive.Content>,
  ComponentPropsWithoutRef<typeof PopoverPrimitive.Content>
>(({ className, sideOffset = 6, collisionPadding = 12, ...props }, ref) => (
  <PopoverPrimitive.Portal>
    <PopoverPrimitive.Content
      ref={ref}
      sideOffset={sideOffset}
      collisionPadding={collisionPadding}
      className={twMerge(
        "z-[1300] max-h-[var(--radix-popover-content-available-height)] origin-[var(--radix-popover-content-transform-origin)] overflow-y-auto rounded-[var(--radius-box)] border border-base-content/10 bg-base-100 text-base-content shadow-xl outline-none",
        className,
      )}
      {...props}
    />
  </PopoverPrimitive.Portal>
));
PopoverContent.displayName = PopoverPrimitive.Content.displayName;
