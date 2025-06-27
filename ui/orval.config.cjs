module.exports = {
  "qdash-file-transfomer": {
    output: {
      client: "react-query",
      mode: "tags-split",
      target: "./src/client",
      schemas: "./src/schemas",
      override: {
        mutator: {
          path: "./src/lib/custom-instance.ts",
          name: "customInstance",
        },
      },
      clean: true,
      mock: false,
    },
    input: {
      target: "../docs/oas/openapi.json",
    },
    // hooks: {
    //   afterAllFilesWrite: "npx eslint . --fix",
    // },
  },
};
