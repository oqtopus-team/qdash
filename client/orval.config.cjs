module.exports = {
  "qdash-file-transfomer": {
    output: {
      client: "react-query",
      mode: "tags-split",
      target: "./src/client",
      schemas: "./src/schemas",
      baseUrl: "http://localhost:5715",
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
