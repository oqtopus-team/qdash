module.exports = {
  "qdash-file-transfomer": {
    output: {
      client: "react-query",
      mode: "tags-split",
      target: "./src/client",
      schemas: "./src/schemas",
      baseUrl: process.env.NEXT_PUBLIC_API_URL,
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
