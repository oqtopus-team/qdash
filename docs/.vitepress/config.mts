import { defineConfig } from "vitepress";
import { withMermaid } from "vitepress-plugin-mermaid";
// https://vitepress.dev/reference/site-config
export default withMermaid(
  defineConfig({
    base: "/qdash/",
    title: "QDash",
    description: "QDash Documentaion",
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
        { text: "Python Client", link: "/python-client" },
      ],

      sidebar: [
        {
          text: "Overview",
          items: [
            { text: "What is QDash", link: "/what-is-qdash" },
            { text: "Quickstart", link: "/quick-start" },
            { text: "Architecture", link: "/architecture" },
            { text: "Python Client", link: "/python-client" },
          ],
        },
        {
          text: "User Guide",
          items: [
            {
              text: "Projects and Data Sharing",
              link: "/projects-and-sharing",
            },
          ],
        },
        {
          text: "Development Guideline",
          items: [
            { text: "Development Flow", link: "/development-flow" },
            {
              text: "Setup Development Environment",
              link: "/setup-development-environment",
            },
            { text: "OpenAPI Specification", link: "/openapi" },
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
