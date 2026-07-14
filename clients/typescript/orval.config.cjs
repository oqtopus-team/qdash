module.exports = {
  qdash: {
    input: {
      target: "../../docs/oas/openapi.json",
    },
    hooks: {
      afterAllFilesWrite: "node ./scripts/format-generated.mjs",
    },
    output: {
      target: "./src/generated/api.ts",
      // Reuse the UI's generated schemas in the repository. The published
      // declarations are bundled by tsup, so the npm package remains standalone.
      schemas: "../../ui/src/schemas",
      client: "axios",
      mode: "single",
      clean: true,
      mock: false,
      override: {
        mutator: {
          path: "./src/orval-request.ts",
          name: "qdashRequest",
        },
      },
    },
  },
};
