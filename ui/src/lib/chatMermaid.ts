import type { MermaidConfig } from "mermaid";

export type MermaidTheme = "dark" | "neutral";

export type MermaidResult = { status: "ok"; svg: string } | { status: "error"; message: string };

/**
 * Settings a chat answer cannot change. `strict` encodes HTML in labels and
 * disables click callbacks; Mermaid also refuses these keys in `%%{init}%%`
 * directives, so a diagram cannot loosen them.
 */
const LOCKED_CONFIG: MermaidConfig = {
  startOnLoad: false,
  securityLevel: "strict",
  suppressErrorRendering: true,
};

const URL_ATTRIBUTES = ["href", "xlink:href", "target"];

/** Rendered diagrams kept for reuse across messages and re-renders. */
const CACHE_LIMIT = 200;

/**
 * Strips what could navigate or run code from a rendered diagram. Strict mode
 * still turns `click A href "..."` into a link, which would navigate away from
 * the conversation, so links keep their label but lose their target.
 */
function neutralizeMermaidSvg(svg: string): string {
  if (typeof DOMParser === "undefined") return svg;
  const doc = new DOMParser().parseFromString(`<body>${svg}</body>`, "text/html");
  for (const script of Array.from(doc.querySelectorAll("script"))) script.remove();
  for (const element of Array.from(doc.body.querySelectorAll("*"))) {
    for (const attribute of Array.from(element.attributes)) {
      const name = attribute.name.toLowerCase();
      if (name.startsWith("on") || (element.localName === "a" && URL_ATTRIBUTES.includes(name))) {
        element.removeAttribute(attribute.name);
      }
    }
  }
  return doc.body.innerHTML;
}

const results = new Map<string, MermaidResult>();
const inflight = new Map<string, Promise<MermaidResult>>();
let queue: Promise<unknown> = Promise.resolve();
let appliedConfig: string | null = null;
let nextId = 0;

const cacheKey = (source: string, theme: MermaidTheme) => `${theme}\0${source}`;

/** A finished render of the diagram, or undefined when it has not run yet. */
export function getMermaidResult(source: string, theme: MermaidTheme): MermaidResult | undefined {
  return results.get(cacheKey(source, theme));
}

function errorMessage(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return typeof error === "string" && error ? error : "Unknown error";
}

/**
 * Renders a diagram, loading Mermaid on first use so chat pages without
 * diagrams never download it. Renders run one at a time because Mermaid keeps
 * global state between `initialize` and `render`.
 */
export function renderMermaid(source: string, theme: MermaidTheme): Promise<MermaidResult> {
  const key = cacheKey(source, theme);
  const done = results.get(key);
  if (done) return Promise.resolve(done);
  const running = inflight.get(key);
  if (running) return running;

  const task = queue
    .then(async (): Promise<MermaidResult> => {
      const mermaid = (await import("mermaid")).default;
      const config: MermaidConfig = { theme, ...LOCKED_CONFIG };
      const configKey = JSON.stringify(config);
      if (appliedConfig !== configKey) {
        mermaid.initialize(config);
        appliedConfig = configKey;
      }
      const { svg } = await mermaid.render(`chat-mermaid-${nextId++}`, source);
      return { status: "ok", svg: neutralizeMermaidSvg(svg) };
    })
    .catch((error: unknown): MermaidResult => ({ status: "error", message: errorMessage(error) }))
    .then((result) => {
      inflight.delete(key);
      if (results.size >= CACHE_LIMIT) {
        const oldest = results.keys().next().value;
        if (oldest !== undefined) results.delete(oldest);
      }
      results.set(key, result);
      return result;
    });
  queue = task;
  inflight.set(key, task);
  return task;
}

/** Forget rendered diagrams and the applied config. For tests. */
export function resetMermaidCache(): void {
  results.clear();
  inflight.clear();
  appliedConfig = null;
  queue = Promise.resolve();
}
