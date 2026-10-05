import { codeBlockOptions } from "@blocknote/code-block";
import {
  BlockNoteSchema,
  createCodeBlockSpec,
  defaultBlockSpecs,
  type CodeBlockOptions,
} from "@blocknote/core";

import { withCodeBlockCopyButton } from "./codeBlockCopyButton";

const supportedLanguages: NonNullable<CodeBlockOptions["supportedLanguages"]> = {
  text: codeBlockOptions.supportedLanguages.text,
  python: codeBlockOptions.supportedLanguages.python,
  shellscript: {
    ...codeBlockOptions.supportedLanguages.shellscript,
    name: "Bash",
  },
  json: codeBlockOptions.supportedLanguages.json,
  yaml: codeBlockOptions.supportedLanguages.yaml,
  sql: codeBlockOptions.supportedLanguages.sql,
  typescript: codeBlockOptions.supportedLanguages.typescript,
  javascript: codeBlockOptions.supportedLanguages.javascript,
  markdown: codeBlockOptions.supportedLanguages.markdown,
};

export const blockNoteSchema = BlockNoteSchema.create({
  blockSpecs: {
    ...defaultBlockSpecs,
    codeBlock: withCodeBlockCopyButton(
      createCodeBlockSpec({
        ...codeBlockOptions,
        defaultLanguage: "text",
        supportedLanguages,
      }),
    ),
  },
});
