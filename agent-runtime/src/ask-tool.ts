import type { JsonValue } from "@earendil-works/chord";
import { defineTool } from "@earendil-works/pi-durable";
import { Type } from "typebox";

/** A question shown to the user as buttons, as stored in the tool result and shown in the UI. */
export interface AskRequest {
  question: string;
  options: Array<{ label: string; description?: string }>;
}

/**
 * Ask the user to pick between concrete options.
 *
 * The UI renders the options as buttons next to a free-text fallback, the way
 * chat products ask for a choice. The turn ends here; the user's pick arrives
 * as the next message.
 */
export const askUserTool = defineTool({
  name: "ask_user",
  description:
    "Ask the user to choose between 2-4 concrete options shown as buttons (they can also type their own answer). " +
    "Use it when you need a decision you cannot make yourself, such as which qubit or task, or whether to proceed. " +
    "Do not use it for open questions or to confirm write operations; those get their own approval card. " +
    "The turn ends after this call.",
  parameters: Type.Object({
    question: Type.String({ description: "One short question." }),
    options: Type.Array(
      Type.Object({
        label: Type.String({ description: "What the button says; sent back as the user's reply." }),
        description: Type.Optional(Type.String({ description: "One line on what this choice means." })),
      }),
      { minItems: 2, maxItems: 4 },
    ),
  }),
  replay: "safe",
  execute: async (params) => {
    const ask: AskRequest = { question: params.question, options: params.options };
    return {
      content: [
        {
          type: "text",
          text: "The question is shown to the user with these options. Stop here; their answer arrives as the next message.",
        },
      ],
      details: { ask } as unknown as JsonValue,
      control: { terminate: true as const },
    };
  },
});
