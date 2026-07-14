import { defineConfig } from "vitepress";
import { withMermaid } from "vitepress-plugin-mermaid";
import { full as emoji } from "markdown-it-emoji";
import taskKnowledgeSidebar from "./task-knowledge-sidebar.json";

// Convert emoji to Fluent Emoji (flat SVG)
function emojiToCodePoints(emoji: string): string {
  return [...emoji]
    .map((char) => char.codePointAt(0)?.toString(16))
    .filter(Boolean)
    .join("-");
}

// https://vitepress.dev/reference/site-config
export default withMermaid(
  defineConfig({
    vite: {
      build: {
        target: "es2022",
      },
    },
    base: "/qdash/",
    title: "QDash",
    description: "Qubit Calibration Management Platform",
    ignoreDeadLinks: true,
    head: [
      [
        "link",
        { rel: "icon", href: "/qdash/oqtopus_logo.svg", type: "image/svg+xml" },
      ],
      ["meta", { name: "theme-color", content: "#1f1fdd" }],
      ["meta", { property: "og:type", content: "website" }],
      ["meta", { property: "og:title", content: "QDash Documentation" }],
      [
        "meta",
        {
          property: "og:description",
          content: "Qubit Calibration Management Platform",
        },
      ],
    ],

    markdown: {
      config: (md) => {
        md.use(emoji);
        md.renderer.rules.emoji = (tokens, idx) => {
          const token = tokens[idx];
          const codePoints = emojiToCodePoints(token.content);
          const cdnUrl = `https://cdn.jsdelivr.net/gh/nicolo-ribaudo/fluentui-emoji-flat-svg@latest/${codePoints}.svg`;
          return `<img src="${cdnUrl}" alt="${token.markup}" class="fluent-emoji" style="height: 1.2em; width: 1.2em; vertical-align: text-bottom; display: inline-block;" />`;
        };
      },
    },

    mermaid: {
      theme: "neutral",
    },
    mermaidPlugin: {
      class: "mermaid my-class",
    },

    themeConfig: {
      logo: "/oqtopus_logo.svg",
      siteTitle: "QDash",

      nav: [
        { text: "Home", link: "/" },
        { text: "Operator Guide", link: "/operator-guide/" },
        { text: "Developer Guide", link: "/developer-guide/" },
        { text: "Reference", link: "/reference/database-structure" },
        {
          text: "Links",
          items: [
            { text: "GitHub", link: "https://github.com/oqtopus-team/qdash" },
            { text: "OQTOPUS", link: "https://github.com/oqtopus-team" },
          ],
        },
      ],

      sidebar: [
        {
          text: "Getting Started",
          items: [
            { text: "What is QDash", link: "/getting-started/what-is-qdash" },
            { text: "Quickstart", link: "/getting-started/quick-start" },
            { text: "Architecture", link: "/getting-started/architecture" },
          ],
        },
        {
          text: "Operator Guide",
          items: [
            { text: "Overview", link: "/operator-guide/" },
            { text: "Setup", link: "/operator-guide/setup" },
            { text: "Operations", link: "/operator-guide/operations" },
            { text: "Workflows", link: "/operator-guide/workflows" },
            {
              text: "Authentication",
              link: "/user-guide/authentication",
            },
            {
              text: "Projects and Sharing",
              link: "/user-guide/projects-and-sharing",
            },
            {
              text: "Dashboard",
              link: "/user-guide/dashboard",
            },
            {
              text: "Cryostats & Cool-downs",
              link: "/user-guide/cryo",
            },
            {
              text: "Python Client",
              link: "/user-guide/qdash-client",
            },
            {
              text: "TypeScript Client",
              link: "/user-guide/qdash-typescript-client",
            },
            {
              text: "Agent Calibration",
              link: "/user-guide/agent-calibration",
            },
          ],
        },
        {
          text: "Developer Guide",
          collapsed: false,
          items: [
            { text: "Overview", link: "/developer-guide/" },
            { text: "Setup", link: "/developer-guide/setup" },
            { text: "Codebase", link: "/developer-guide/codebase" },
            { text: "Commands", link: "/developer-guide/commands" },
            { text: "Testing", link: "/developer-guide/testing" },
          ],
        },
        {
          text: "Developer Deep Dives",
          collapsed: true,
          items: [
            { text: "Development Flow", link: "/development/development-flow" },
            { text: "Full Setup Notes", link: "/development/setup" },
            {
              text: "API",
              collapsed: true,
              items: [
                { text: "Design Guidelines", link: "/development/api/design" },
                { text: "Testing", link: "/development/api/testing" },
              ],
            },
            {
              text: "Workflow",
              collapsed: true,
              items: [
                { text: "Quickstart", link: "/development/workflow/quickstart" },
                { text: "Engine Architecture", link: "/development/workflow/engine-architecture" },
                { text: "Testing", link: "/development/workflow/testing" },
              ],
            },
            {
              text: "UI",
              collapsed: true,
              items: [
                { text: "Guidelines", link: "/development/ui/guidelines" },
                { text: "Design Policy", link: "/development/ui/design-policy" },
                { text: "Architecture", link: "/development/ui/architecture" },
                { text: "Testing", link: "/development/ui/testing" },
              ],
            },
            {
              text: "Copilot",
              collapsed: true,
              items: [
                { text: "Architecture", link: "/development/copilot/architecture" },
                { text: "AI Review Evals", link: "/development/copilot/ai-review-evals" },
                { text: "Sandbox", link: "/development/copilot/sandbox" },
                { text: "LLM Agent", link: "/development/copilot/agent" },
                { text: "LLM Integration Patterns", link: "/development/copilot/llm-integration-patterns" },
                { text: "SSE Streaming", link: "/development/copilot/streaming" },
                { text: "Tool Result Compression", link: "/development/copilot/tool-result-compression" },
              ],
            },
            {
              text: "Issues",
              collapsed: true,
              items: [
                { text: "Architecture", link: "/development/issues/architecture" },
              ],
            },
            { text: "Datetime Handling", link: "/development/datetime" },
            { text: "Logging", link: "/development/logging" },
            { text: "QID Validation", link: "/development/qid-validation" },
            { text: "Credential Scanning", link: "/development/credential-scan" },
            { text: "Docs Guidelines", link: "/development/docs-guidelines" },
          ],
        },
        {
          text: "Reference",
          collapsed: false,
          items: [
            {
              text: "Database Structure",
              link: "/reference/database-structure",
            },
            { text: "Database Indexes", link: "/reference/database-indexes" },
            { text: "Migration to v1.8.0", link: "/reference/migration-v1.8.0" },
            { text: "OpenAPI", link: "/reference/openapi" },
          ],
        },
        {
          text: "Task Knowledge",
          collapsed: false,
          link: "/task-knowledge/",
          items: taskKnowledgeSidebar,
        },
        {
          text: "Architecture Deep Dives",
          collapsed: true,
          items: [
            { text: "Overview", link: "/architecture/README" },
            {
              text: "1-Qubit Scheduler",
              link: "/architecture/one-qubit-scheduler",
            },
            {
              text: "Ordering Plugins",
              link: "/architecture/one-qubit-ordering-plugins",
            },
            { text: "CR Scheduler", link: "/architecture/cr-scheduler" },
            {
              text: "Square Lattice",
              link: "/architecture/square-lattice-topology",
            },
            { text: "Notes", link: "/architecture/notes" },
          ],
        },
        {
          text: "Community",
          collapsed: true,
          items: [
            { text: "Contributing", link: "/CONTRIBUTING" },
            { text: "Code of Conduct", link: "/CODE_OF_CONDUCT" },
            { text: "Security", link: "/SECURITY" },
          ],
        },
      ],

      socialLinks: [
        { icon: "github", link: "https://github.com/oqtopus-team/qdash" },
      ],

      footer: {
        message: "Released under the Apache 2.0 License.",
        copyright: "Copyright © 2024-present OQTOPUS Team",
      },

      search: {
        provider: "local",
      },

      editLink: {
        pattern:
          "https://github.com/oqtopus-team/qdash/edit/develop/docs/:path",
        text: "Edit this page on GitHub",
      },

      lastUpdated: {
        text: "Updated at",
        formatOptions: {
          dateStyle: "medium",
        },
      },
    },
  }),
);
