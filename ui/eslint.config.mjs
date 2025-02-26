import tsEslint from "@typescript-eslint/eslint-plugin";
import importPlugin from "eslint-plugin-import";
import reactHooks from "eslint-plugin-react-hooks";

export default [
  {
    languageOptions: {
      ecmaVersion: 2020,
      sourceType: "module",
      globals: {
        window: "readonly",
        document: "readonly",
        navigator: "readonly",
        process: "readonly",
        __dirname: "readonly",
        __filename: "readonly",
      },
      parser: (await import("@typescript-eslint/parser")).default,
    },
    ignores: ["dist", ".eslintrc.cjs"],
    plugins: {
      import: importPlugin,
      "react-hooks": reactHooks,
      "@typescript-eslint": tsEslint,
    },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      "import/order": [
        "error",
        {
          groups: [
            "builtin",
            "external",
            "parent",
            "sibling",
            "index",
            "object",
            "type",
          ],
          pathGroups: [
            {
              pattern: "{react,react-dom/**,next/**}",
              group: "builtin",
              position: "before",
            },
            {
              pattern: "@src/**",
              group: "parent",
              position: "before",
            },
          ],
          pathGroupsExcludedImportTypes: ["builtin"],
          alphabetize: { order: "asc" },
          "newlines-between": "always",
        },
      ],
      "@typescript-eslint/no-unused-vars": "off",
      "@typescript-eslint/no-explicit-any": "off",
      "@typescript-eslint/consistent-type-imports": [
        "error",
        { prefer: "type-imports" },
      ],
    },
  },
];
