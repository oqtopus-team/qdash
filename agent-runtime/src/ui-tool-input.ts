import { Type, type Static, type TSchema } from "typebox";

// See ui-tool.ts for why this path resolves in the image too.
import { UI_COMPONENT_TYPES, type UiSpec } from "../../ui/src/lib/copilotUiSpec.ts";

/**
 * The arguments `render_ui` declares to the model, and their mapping to and
 * from the stored json-render spec.
 *
 * The stored spec keys elements by arbitrary ids and gives each component its
 * own props, which a strict JSON schema cannot express: providers that sample
 * tool arguments against a schema (`constrainedSampling`) reject maps with
 * free keys (`patternProperties`), schema-valued `additionalProperties`, and
 * unions of object shapes. So the model sends one list per component type,
 * each element carrying its `id`, and table rows as cell lists in column
 * order. Plotly traces and layout stay free-form, so a Chart sends them as
 * JSON text. `specFromToolArgs` turns the arguments back into the stored
 * spec, which the shared catalog validates as before.
 *
 * Keep the schema inside what pi's `makeStrictJsonSchema` accepts, without the
 * keywords Anthropic's strict mode rejects (`maxItems`, `minimum`, ...), and
 * with few optional or union-typed fields: Anthropic and Bedrock reject more
 * than 16 across all strict tools. ui-tool.test.mjs checks all three.
 */

/** The argument list holding each component type's elements, in catalog order. */
export const UI_INPUT_GROUPS = {
  Stack: "stacks",
  Card: "cards",
  Metric: "metrics",
  Table: "tables",
  Alert: "alerts",
  Text: "texts",
  Chart: "charts",
  Link: "links",
} as const satisfies Record<(typeof UI_COMPONENT_TYPES)[number], string>;

type UiComponentType = keyof typeof UI_INPUT_GROUPS;
type UiInputGroup = (typeof UI_INPUT_GROUPS)[UiComponentType];

const CONTAINER_TYPES: ReadonlySet<UiComponentType> = new Set(["Stack", "Card"]);

const str = (description: string) => Type.String({ description });
const choice = (values: readonly string[], description: string) =>
  // `{ type, enum }` rather than a literal union, for vLLM guided decoding.
  Type.Unsafe<string>({ type: "string", enum: [...values], description });
const element = (properties: Record<string, TSchema>, children: boolean) =>
  Type.Object(
    {
      id: str("Unique element id: letters, digits, - and _."),
      ...properties,
      ...(children
        ? { children: Type.Array(Type.String(), { description: "Ids of the child elements, in order." }) }
        : {}),
    },
    { additionalProperties: false },
  );
const list = (item: TSchema, description: string) => Type.Array(item, { description });

const cell = Type.Union([Type.String(), Type.Number(), Type.Boolean(), Type.Null()]);
const TONES = ["neutral", "info", "success", "warning", "error"] as const;

export const UI_TOOL_PARAMETERS = Type.Object(
  {
    root: str("Id of the top element."),
    stacks: list(
      element(
        {
          direction: Type.Optional(choice(["vertical", "horizontal"], "Default vertical.")),
          gap: Type.Optional(choice(["sm", "md", "lg"], "Default md.")),
        },
        true,
      ),
      "Stack layout containers.",
    ),
    cards: list(
      element({ title: Type.Optional(Type.String()), description: Type.Optional(Type.String()) }, true),
      "Card groups.",
    ),
    metrics: list(
      element(
        {
          label: Type.String(),
          value: Type.Union([Type.String(), Type.Number()]),
          unit: Type.Optional(Type.String()),
          detail: Type.Optional(Type.String()),
          tone: Type.Optional(choice(TONES, "Default neutral.")),
        },
        false,
      ),
      "Metric values.",
    ),
    tables: list(
      element(
        {
          caption: Type.Optional(Type.String()),
          columns: Type.Array(
            Type.Object(
              {
                key: str("Column key: letters, digits, - and _."),
                label: Type.String(),
                align: Type.Optional(choice(["left", "right"], "Right-align numbers.")),
              },
              { additionalProperties: false },
            ),
          ),
          rows: Type.Array(Type.Array(cell), {
            description: "Each row lists one cell per column, in column order; null for an empty cell.",
          }),
        },
        false,
      ),
      "Tables.",
    ),
    alerts: list(
      element(
        {
          tone: choice(["info", "success", "warning", "error"], "Status of the message."),
          title: Type.Optional(Type.String()),
          message: Type.String(),
        },
        false,
      ),
      "Status messages.",
    ),
    texts: list(
      element(
        {
          text: Type.String(),
          variant: Type.Optional(choice(["body", "muted", "heading"], "Default body.")),
        },
        false,
      ),
      "Plain text blocks.",
    ),
    charts: list(
      element(
        {
          data: str("JSON array of Plotly traces, as text."),
          layout: Type.Optional(str("JSON object of the Plotly layout, as text.")),
        },
        false,
      ),
      "Plotly charts.",
    ),
    links: list(
      element({ label: Type.String(), href: str("A QDash path, such as /chip/{chipId}/qubit/{qid}.") }, false),
      "Links to QDash pages.",
    ),
  },
  { additionalProperties: false },
);

/** The arguments as `parameters` declares them; the harness validates them after `prepareArguments`. */
export type UiToolArgs = Static<typeof UI_TOOL_PARAMETERS>;
type InputElement = Record<string, unknown> & { id: string; children?: string[] };

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/**
 * The stored spec the arguments describe, or the problems that stop the
 * mapping. The spec is not yet checked against the catalog; that is
 * `validateUiSpec`'s job.
 */
export function specFromToolArgs(
  args: UiToolArgs,
): { ok: true; spec: unknown } | { ok: false; errors: string[] } {
  const errors: string[] = [];
  const elements: [string, unknown][] = [];
  const seen = new Set<string>();
  for (const [type, group] of Object.entries(UI_INPUT_GROUPS) as [UiComponentType, UiInputGroup][]) {
    const items = (args[group] ?? []) as InputElement[];
    items.forEach((item, index) => {
      const where = `${group}[${index}]`;
      const { id, children, ...fields } = item;
      if (seen.has(id)) errors.push(`${where}: element id "${id}" is used by another element`);
      seen.add(id);
      const props = propsFromInput(type, fields, where, errors);
      if (props) {
        elements.push([id, { type, props, children: CONTAINER_TYPES.has(type) ? (children ?? []) : [] }]);
      }
    });
  }
  if (errors.length > 0) return { ok: false, errors };
  // fromEntries defines own properties, so no id can reach a prototype.
  return { ok: true, spec: { root: args.root, elements: Object.fromEntries(elements) } };
}

function propsFromInput(
  type: UiComponentType,
  fields: Record<string, unknown>,
  where: string,
  errors: string[],
): Record<string, unknown> | undefined {
  // An omitted optional field arrives as null from strict sampling.
  const props = Object.fromEntries(Object.entries(fields).filter(([, value]) => value != null));
  if (type === "Table") {
    const columns = Array.isArray(props.columns) ? (props.columns as { key?: unknown }[]) : [];
    const rows = Array.isArray(props.rows) ? (props.rows as unknown[][]) : [];
    const before = errors.length;
    props.rows = rows.map((row, r) => {
      if (row.length > columns.length) {
        errors.push(
          `${where}.rows[${r}] has ${row.length} cells but the table has ${columns.length} columns`,
        );
      }
      return Object.fromEntries(columns.map((column, c) => [String(column.key), row[c] ?? null]));
    });
    return errors.length > before ? undefined : props;
  }
  if (type === "Chart") {
    const before = errors.length;
    const { layout, ...rest } = props;
    const parsed = {
      ...rest,
      data: parseJsonText(props.data, `${where}.data`, "array", errors),
      ...(layout === undefined || layout === ""
        ? {}
        : { layout: parseJsonText(layout, `${where}.layout`, "object", errors) }),
    };
    return errors.length > before ? undefined : parsed;
  }
  return props;
}

/** Longest Chart `data` or `layout` text that is parsed. */
const MAX_JSON_TEXT_LENGTH = 200_000;

function parseJsonText(
  value: unknown,
  where: string,
  kind: "array" | "object",
  errors: string[],
): unknown {
  if (typeof value !== "string") {
    errors.push(`${where} must be JSON text`);
    return undefined;
  }
  if (value.length > MAX_JSON_TEXT_LENGTH) {
    errors.push(`${where} is ${value.length} characters; the limit is ${MAX_JSON_TEXT_LENGTH}`);
    return undefined;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(value);
  } catch (error) {
    errors.push(`${where} is not valid JSON (${error instanceof Error ? error.message : String(error)})`);
    return undefined;
  }
  if (kind === "array" ? !Array.isArray(parsed) : !isPlainObject(parsed)) {
    errors.push(`${where} must hold a JSON ${kind}`);
    return undefined;
  }
  return parsed;
}

/**
 * The arguments that describe a stored spec, for calls in the earlier
 * `{ spec }` form. Expects a spec `validateUiSpec` accepted. Table row keys
 * outside the columns are dropped and missing cells become null; the chat
 * shows neither differently.
 */
export function toolArgsFromSpec(spec: UiSpec): UiToolArgs {
  const args: Record<string, unknown> = { root: spec.root };
  for (const group of Object.values(UI_INPUT_GROUPS)) args[group] = [];
  for (const [id, element] of Object.entries(spec.elements)) {
    const type = element.type as UiComponentType;
    const props: Record<string, unknown> = { ...element.props };
    if (type === "Table") {
      const columns = props.columns as { key: string }[];
      props.rows = (props.rows as Record<string, unknown>[]).map((row) =>
        columns.map((column) =>
          Object.prototype.hasOwnProperty.call(row, column.key) ? row[column.key] : null,
        ),
      );
    }
    if (type === "Chart") {
      props.data = JSON.stringify(props.data);
      if (props.layout !== undefined) props.layout = JSON.stringify(props.layout);
    }
    (args[UI_INPUT_GROUPS[type]] as unknown[]).push({
      id,
      ...props,
      ...(CONTAINER_TYPES.has(type) ? { children: element.children } : {}),
    });
  }
  return args as UiToolArgs;
}
