import { defineConfig } from "vitepress";
import { withMermaid } from "vitepress-plugin-mermaid";
// https://vitepress.dev/reference/site-config
export default withMermaid(
  defineConfig({
    base: "/qdash/",
    title: "QDash",
    description: "QDash Documentation",
    ignoreDeadLinks: true,
    mermaid: {
      // refer https://mermaid.js.org/config/setup/modules/mermaidAPI.html#mermaidapi-configuration-defaults for options
    },
    // optionally set additional config for plugin itself with MermaidPluginConfig
    mermaidPlugin: {
      class: "mermaid my-class", // set additional css classes for parent container
    },

    themeConfig: {
      // https://vitepress.dev/reference/default-theme-config
      logo: "/oqtopus-symbol.png",
      nav: [
        { text: "Home", link: "/" },
        { text: "What is QDash", link: "/what-is-qdash" },
        { text: "Quickstart", link: "/quick-start" },
      ],

      sidebar: [
        {
          text: "Getting Started",
          items: [
            { text: "What is QDash", link: "/what-is-qdash" },
            { text: "Quickstart", link: "/quick-start" },
            { text: "Architecture", link: "/architecture" },
          ],
        },
        {
          text: "User Guide",
          items: [
            { text: "Projects and Data Sharing", link: "/projects-and-sharing" },
          ],
        },
        {
          text: "Development Guide",
          collapsed: false,
          items: [
            { text: "Development Flow", link: "/guide/development-flow" },
            { text: "Setup Environment", link: "/guide/setup-development-environment" },
            { text: "API Design Guidelines", link: "/guide/api-design-guidelines" },
            { text: "API Testing Guidelines", link: "/guide/api-testing-guidelines" },
            { text: "Workflow Testing Guidelines", link: "/guide/workflow-testing-guidelines" },
          ],
        },
        {
          text: "Reference",
          collapsed: false,
          items: [
            { text: "Database Structure", link: "/reference/database-structure" },
            { text: "Database Indexes", link: "/reference/database-indexes" },
            { text: "OpenAPI Specification", link: "/reference/openapi" },
          ],
        },
        {
          text: "Architecture Details",
          collapsed: true,
          items: [
            { text: "Overview", link: "/architecture/README" },
            { text: "One-Qubit Scheduler", link: "/architecture/one-qubit-scheduler" },
            { text: "Ordering Plugins", link: "/architecture/one-qubit-ordering-plugins" },
            { text: "CR Scheduler", link: "/architecture/cr-scheduler" },
            { text: "Square Lattice Topology", link: "/architecture/square-lattice-topology" },
          ],
        },
        {
          text: "Community",
          collapsed: true,
          items: [
            { text: "How to Contribute", link: "/CONTRIBUTING" },
            { text: "Code of Conduct", link: "/CODE_OF_CONDUCT" },
            { text: "Security", link: "/SECURITY" },
          ],
        },
      ],

      socialLinks: [
        {
          icon: "github",
          link: "https://github.com/oqtopus-team/qdash",
        },
      ],
    },
  }),
);
