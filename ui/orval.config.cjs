module.exports = {
  "qdash-file-transfomer": {
    output: {
      client: "react-query",
      mode: "tags-split",
      target: "./src/client",
      schemas: "./src/schemas",
      baseUrl: "http://localhost:5716",
      clean: true,
      mock: false,
      headers: {
        "X-User-ID": "default_user",
      },
    },
    input: {
      target: "../docs/oas/openapi.json",
    },
    // hooks: {
    //   afterAllFilesWrite: "npx eslint . --fix",
    // },
  },
};
