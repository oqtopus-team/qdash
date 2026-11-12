import { z } from "zod";

/** Splits comma-separated tags into trimmed, non-empty tags in their written order. */
function parseFlowTags(value: string): string[] {
  return value
    .split(",")
    .map((tag) => tag.trim())
    .filter(Boolean);
}

/**
 * Flow metadata written in the New Flow form and the workflow editor. Values are trimmed, tags
 * become the array a `SaveFlowRequest` carries, and an empty entrypoint is left out of the request.
 */
export const flowMetadataSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, "Please enter a flow name")
    .regex(
      /^[a-zA-Z0-9_]+$/,
      "Flow name must contain only alphanumeric characters and underscores",
    ),
  description: z.string().trim(),
  flow_function_name: z.string().transform((value) => value.trim() || undefined),
  username: z.string().trim().min(1, "Please enter a username"),
  tags: z.string().transform(parseFlowTags),
  folder: z.string().trim(),
});

/**
 * Properties of a saved flow in the workflow editor: the flow name is fixed by the route, and the
 * chip and the default interval are edited next to the shared metadata.
 */
export const flowPropertiesSchema = flowMetadataSchema.omit({ name: true }).extend({
  chip_id: z.string().trim(),
  default_interval: z.string().trim(),
});

export type FlowMetadataFormInput = z.input<typeof flowMetadataSchema>;
export type FlowMetadataFormData = z.output<typeof flowMetadataSchema>;
export type FlowPropertiesFormInput = z.input<typeof flowPropertiesSchema>;
export type FlowPropertiesFormData = z.output<typeof flowPropertiesSchema>;
