import type { MermaidConfig as MermaidLibraryConfig } from "mermaid";
import type { DiagramPlugin } from "streamdown";

type MermaidInstance = ReturnType<DiagramPlugin["getMermaid"]>;
type MermaidConfig = Parameters<MermaidInstance["initialize"]>[0];

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

/**
 * A Streamdown diagram plugin that loads Mermaid only when a diagram first
 * renders, so chat pages without diagrams never download it.
 */
export function createLazyMermaidPlugin(): DiagramPlugin {
  let requested: MermaidConfig = {};
  let applied: string | null = null;
  const instance: MermaidInstance = {
    initialize(config) {
      requested = config;
    },
    async render(id, source) {
      const mermaid = (await import("mermaid")).default;
      const config = { ...requested, ...LOCKED_CONFIG };
      const key = JSON.stringify(config);
      if (applied !== key) {
        // Streamdown types the config loosely; values come from ChatMarkdown and LOCKED_CONFIG.
        mermaid.initialize(config as MermaidLibraryConfig);
        applied = key;
      }
      const { svg } = await mermaid.render(id, source);
      return { svg: neutralizeMermaidSvg(svg) };
    },
  };
  return {
    name: "mermaid",
    type: "diagram",
    language: "mermaid",
    getMermaid(config) {
      if (config) instance.initialize(config);
      return instance;
    },
  };
}
