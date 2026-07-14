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
      schemas: "./src/generated/models",
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
