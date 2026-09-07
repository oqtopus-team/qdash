module.exports = {
  "qdash-file-transfomer": {
    output: {
      client: "react-query",
      httpClient: "axios",
      mode: "tags-split",
      target: "./src/client",
      schemas: "./src/schemas",
      override: {
        aliasCombinedTypes: true,
        mutator: {
          path: "./src/lib/api/custom-instance.ts",
          name: "customInstance",
        },
      },
      clean: true,
      mock: false,
    },
    input: {
      target: "../docs/oas/openapi.json",
    },
    hooks: {
      afterAllFilesWrite:
        "node ../clients/typescript/scripts/format-generated.mjs ./src/client ./src/schemas",
    },
  },
};
