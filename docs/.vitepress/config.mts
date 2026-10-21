import { defineConfig } from "vitepress";
import { withMermaid } from "vitepress-plugin-mermaid";
import { full as emoji } from "markdown-it-emoji";

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
    ignoreDeadLinks: [
      /^https?:\/\/(?:localhost|127\.0\.0\.1)(?::\d+)?(?:\/.*)?$/,
      /^\.\/(?:box-setup|cw-characterization|td-characterization|one-qubit-gate-calibration|two-qubit-gate-calibration|benchmarking|ChevronPattern)(?:\/|$)/,
    ],
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

      // Two readers, two guides (docs/developer-guide/docs-guidelines.md).
      nav: [
        { text: "Home", link: "/" },
        { text: "User Guide", link: "/user-guide/" },
        { text: "Developer Guide", link: "/developer-guide/" },
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
          text: "User Guide",
          items: [
            { text: "Overview", link: "/user-guide/" },
            { text: "What is QDash", link: "/user-guide/what-is-qdash" },
            {
              text: "Set Up and Operate",
              items: [
                {
                  text: "Setup",
                  items: [
                    { text: "Choose a Backend", link: "/user-guide/setup" },
                    { text: "Fake Backend", link: "/user-guide/setup/fake-backend" },
                    { text: "Qubex Backend", link: "/user-guide/setup/qubex-backend" },
                  ],
                },
                { text: "Operations", link: "/user-guide/operations" },
                { text: "System Updates", link: "/user-guide/system-updates" },
              ],
            },
            {
              text: "Work in QDash",
              items: [
                { text: "Application Tour", link: "/user-guide/application-tour" },
                {
                  text: "Authentication and Users",
                  link: "/user-guide/authentication-and-users",
                },
                {
                  text: "Projects and Data Sharing",
                  link: "/user-guide/projects-and-data-sharing",
                },
                { text: "Dashboard", link: "/user-guide/dashboard" },
                { text: "Running Calibrations", link: "/user-guide/running-calibrations" },
                { text: "Task Parameters", link: "/user-guide/task-parameters" },
                { text: "Data and Provenance", link: "/user-guide/data-and-provenance" },
                { text: "Reviewing Results", link: "/user-guide/reviewing-results" },
                { text: "AI Evaluations", link: "/user-guide/ai-evaluations" },
                { text: "AI Chat", link: "/user-guide/ai-chat" },
                { text: "Agent Calibration", link: "/user-guide/agent-calibration" },
                {
                  text: "Cryostats and Cool-downs",
                  link: "/user-guide/cryostats-and-cool-downs",
                },
              ],
            },
          ],
        },
        {
          text: "Developer Guide",
          items: [
            { text: "Overview", link: "/developer-guide/" },
            { text: "Architecture", link: "/developer-guide/architecture" },
            { text: "Setup", link: "/developer-guide/setup" },
            { text: "Codebase", link: "/developer-guide/codebase" },
            { text: "Commands", link: "/developer-guide/commands" },
            { text: "Testing", link: "/developer-guide/testing" },
            { text: "Development Flow", link: "/developer-guide/development-flow" },
            { text: "Docs Guidelines", link: "/developer-guide/docs-guidelines" },
            {
              text: "Conventions",
              collapsed: true,
              items: [
                { text: "Datetime Handling", link: "/developer-guide/conventions/datetime" },
                { text: "Logging", link: "/developer-guide/conventions/logging" },
                { text: "Credential Scanning", link: "/developer-guide/conventions/credential-scan" },
              ],
            },
            {
              text: "API",
              collapsed: true,
              items: [
                { text: "Design Guidelines", link: "/developer-guide/api/design" },
                { text: "Contracts", link: "/developer-guide/api/contracts" },
                { text: "Code Structure", link: "/developer-guide/api/structure" },
                { text: "Testing", link: "/developer-guide/api/testing" },
              ],
            },
            {
              text: "UI",
              collapsed: true,
              items: [
                { text: "Architecture", link: "/developer-guide/ui/architecture" },
                { text: "Guidelines", link: "/developer-guide/ui/guidelines" },
                { text: "API Integration", link: "/developer-guide/ui/api-integration" },
                { text: "Design Policy", link: "/developer-guide/ui/design-policy" },
                { text: "Testing", link: "/developer-guide/ui/testing" },
              ],
            },
            {
              text: "Workflow",
              collapsed: true,
              items: [
                { text: "Quickstart", link: "/developer-guide/workflow/quickstart" },
                { text: "Engine Architecture", link: "/developer-guide/workflow/engine-architecture" },
                { text: "Services", link: "/developer-guide/workflow/services" },
                { text: "Calibration Pipeline Spec", link: "/developer-guide/workflow/calibration-pipeline" },
                { text: "Calibration Data Lifecycle", link: "/developer-guide/workflow/calibration-data-lifecycle" },
                { text: "Parameter Resolution", link: "/developer-guide/workflow/parameter-resolution" },
                { text: "Frequency Parameter Policy", link: "/developer-guide/workflow/frequency-parameter-policy" },
                { text: "Testing", link: "/developer-guide/workflow/testing" },
              ],
            },
            {
              text: "Copilot",
              collapsed: true,
              items: [
                { text: "Architecture", link: "/developer-guide/copilot/architecture" },
                { text: "Agent Platform", link: "/developer-guide/copilot/agent-platform" },
                { text: "Knowledge Layout", link: "/developer-guide/copilot/knowledge-layout" },
                { text: "Calibration Evaluation", link: "/developer-guide/copilot/evaluation" },
                { text: "Python Sandbox", link: "/developer-guide/copilot/python-sandbox" },
                { text: "Chat Streaming", link: "/developer-guide/copilot/chat-streaming" },
              ],
            },
            {
              text: "Architecture Deep Dives",
              collapsed: true,
              items: [
                { text: "1-Qubit Scheduler", link: "/developer-guide/architecture/one-qubit-scheduler" },
                { text: "Ordering Strategies", link: "/developer-guide/architecture/one-qubit-ordering-strategies" },
                { text: "CR Scheduler", link: "/developer-guide/architecture/cr-scheduler" },
                { text: "Square Lattice", link: "/developer-guide/architecture/square-lattice-topology" },
                { text: "Notes", link: "/developer-guide/architecture/notes" },
                { text: "Provenance", link: "/developer-guide/architecture/provenance" },
              ],
            },
            {
              text: "Reference",
              collapsed: true,
              items: [
                { text: "Overview", link: "/reference/" },
                { text: "Database Collections", link: "/reference/database-structure" },
                { text: "OpenAPI", link: "/reference/openapi" },
                { text: "Python Client", link: "/reference/clients/python" },
                { text: "TypeScript Client", link: "/reference/clients/typescript" },
              ],
            },
            {
              text: "Docs Tooling",
              collapsed: true,
              items: [
                { text: "Demo GIFs", link: "/demos/README" },
                { text: "Demo Video", link: "/demos/video/README" },
              ],
            },
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
