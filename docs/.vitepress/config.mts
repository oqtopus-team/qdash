import { defineConfig } from "vitepress";
import { withMermaid } from "vitepress-plugin-mermaid";

// https://vitepress.dev/reference/site-config
export default withMermaid(
  defineConfig({
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
        { text: "Guide", link: "/getting-started/what-is-qdash" },
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
          text: "User Guide",
          items: [
            {
              text: "Authentication",
              link: "/user-guide/authentication",
            },
            {
              text: "Projects and Sharing",
              link: "/user-guide/projects-and-sharing",
            },
          ],
        },
        {
          text: "Development",
          collapsed: false,
          items: [
            {
              text: "Development Flow",
              link: "/development/development-flow",
            },
            { text: "Setup", link: "/development/setup" },
            {
              text: "API",
              collapsed: true,
              items: [
                { text: "Design Guidelines", link: "/development/api/design" },
                { text: "Testing", link: "/development/api/testing" },
              ],
            },
            {
              text: "UI",
              collapsed: true,
              items: [
                { text: "Guidelines", link: "/development/ui/guidelines" },
                { text: "Architecture", link: "/development/ui/architecture" },
                { text: "Testing", link: "/development/ui/testing" },
              ],
            },
            {
              text: "Workflow",
              collapsed: true,
              items: [
                { text: "Testing", link: "/development/workflow/testing" },
              ],
            },
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
            { text: "OpenAPI", link: "/reference/openapi" },
          ],
        },
        {
          text: "Architecture Details",
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
