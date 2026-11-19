/**
 * What an explicit link anywhere in the app points at, for its hover card.
 *
 * Describing a link reads only its attributes and the current location: it
 * never requests the destination. A QDash record route (task result,
 * execution, forum post, figure) on this origin is named as that record, so
 * the card can load a summary when it opens; the same path on another host is
 * an external link. Chat answers are the one exception (`scope: "chat"`): they
 * keep the record leniency described in `chatLinks.ts`, so a hover card agrees
 * with what clicking the link opens.
 */

import { getNavigationSections, isPathWithin } from "@/components/layout/navigation";
import { matchRecordRoute, type RecordLink } from "@/lib/chatLinks";

/** Where a link is rendered: chat answers keep their historical host leniency. */
export type LinkScope = "app" | "chat";

export type LinkDescription = (
  | RecordLink
  | { kind: "fragment"; href: string; id: string; label: string | null }
  | { kind: "page"; href: string; path: string; section: string | null }
  | { kind: "api"; href: string; path: string }
  | { kind: "download"; href: string; filename: string }
  | { kind: "email"; href: string; address: string }
  | { kind: "phone"; href: string; number: string }
  | { kind: "external"; href: string; host: string }
  | { kind: "other"; href: string; scheme: string }
) & {
  /** The browser opens the link in another tab or window. */
  newTab: boolean;
};

interface PageLocation {
  origin: string;
  pathname: string;
  search: string;
}

export interface LinkInput {
  href: string;
  /** The `download` attribute: null when absent, "" when present without a name. */
  download?: string | null;
  target?: string | null;
  scope?: LinkScope;
  /** The page the link is on; defaults to the current one. */
  location?: PageLocation;
  /** The visible name of the element a fragment points at, if it exists. */
  resolveFragment?: (id: string) => string | null;
}

const SECTION_ALIASES = [{ href: "/executions", label: "Execution" }];

/** Every sidebar destination, longest path first, so nested routes win. */
const SECTIONS = [
  ...getNavigationSections({ canEdit: true, isAdmin: true }).flatMap((section) =>
    section.items.map(({ href, label }) => ({ href, label })),
  ),
  ...SECTION_ALIASES,
].sort((a, b) => b.href.length - a.href.length);

/** The sidebar section a QDash path belongs to, such as "Chip" for `/chip/64Qv3`. */
export function pageSection(pathname: string): string | null {
  return SECTIONS.find((item) => isPathWithin(pathname, item.href))?.label ?? null;
}

function decode(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function currentLocation(): PageLocation {
  if (typeof window === "undefined")
    return { origin: "http://localhost", pathname: "/", search: "" };
  const { origin, pathname, search } = window.location;
  return { origin, pathname, search };
}

function opensNewTab(target: string | null | undefined): boolean {
  if (!target) return false;
  return !["_self", "_top", "_parent"].includes(target.toLowerCase());
}

function fileName(url: URL): string {
  const last = url.pathname.split("/").filter(Boolean).pop();
  return last ? decode(last) : url.host || url.href;
}

/**
 * Describe a link for its hover card, or null when it has no destination to describe:
 * an empty href, a bare `#` placeholder, `javascript:` or an unparseable URL.
 */
export function describeLink(input: LinkInput): LinkDescription | null {
  const href = input.href.trim();
  if (!href || href === "#" || /^javascript:/i.test(href)) return null;
  const location = input.location ?? currentLocation();
  const newTab = opensNewTab(input.target);

  let url: URL;
  try {
    url = new URL(href, `${location.origin}${location.pathname}${location.search}`);
  } catch {
    return null;
  }

  switch (url.protocol) {
    case "mailto:":
      return { kind: "email", href, address: decode(url.pathname), newTab };
    case "tel:":
    case "sms:":
      return { kind: "phone", href, number: decode(url.pathname), newTab };
    case "http:":
    case "https:":
      break;
    default:
      if (input.download !== null && input.download !== undefined) {
        return { kind: "download", href, filename: input.download || fileName(url), newTab };
      }
      return { kind: "other", href, scheme: url.protocol.replace(/:$/, ""), newTab };
  }

  if (input.download !== null && input.download !== undefined) {
    return { kind: "download", href, filename: input.download || fileName(url), newTab };
  }

  const sameOrigin = url.origin === location.origin;
  if (
    sameOrigin &&
    url.hash.length > 1 &&
    url.pathname === location.pathname &&
    url.search === location.search
  ) {
    const id = decode(url.hash.slice(1));
    return { kind: "fragment", href, id, label: input.resolveFragment?.(id) ?? null, newTab };
  }

  if (sameOrigin || input.scope === "chat") {
    const record = matchRecordRoute(url, href);
    if (record) return { ...record, newTab };
  }
  if (!sameOrigin) return { kind: "external", href, host: url.host, newTab };

  const path = `${url.pathname}${url.search}${url.hash}`;
  if (isPathWithin(url.pathname, "/api")) return { kind: "api", href, path, newTab };
  return { kind: "page", href, path, section: pageSection(url.pathname), newTab };
}
