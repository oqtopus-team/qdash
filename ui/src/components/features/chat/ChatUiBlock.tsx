"use client";

import {
  Component,
  createContext,
  memo,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  JSONUIProvider,
  Renderer,
  defineRegistry,
  type ComponentRegistry,
  type ComponentRenderProps,
} from "@json-render/react";
import type { Spec } from "@json-render/core";
import { AlertTriangle, CheckCircle2, Info, XCircle } from "lucide-react";
import { ChatMarkdown, ChatLink } from "@/components/features/chat/ChatMarkdown";
import { ChatPlotlyChart } from "@/components/features/chat/ChatPlotlyChart";
import { parseUiBlock, safeInternalHref, uiCatalog } from "@/lib/copilotUiSpec";

type Tone = "neutral" | "info" | "success" | "warning" | "error";

// Status is shown with an icon and a label as well as color.
const TONE_ICON = {
  info: { Icon: Info, label: "Info", text: "text-info" },
  success: { Icon: CheckCircle2, label: "OK", text: "text-success" },
  warning: { Icon: AlertTriangle, label: "Warning", text: "text-warning" },
  error: { Icon: XCircle, label: "Error", text: "text-error" },
} as const;

const ALERT_CLASS = {
  info: "alert-info",
  success: "alert-success",
  warning: "alert-warning",
  error: "alert-error",
} as const;

const GAP_CLASS = { sm: "gap-2", md: "gap-3", lg: "gap-4" } as const;

function formatCell(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  return String(value);
}

/** Reports a failed element to the block, which then shows its fallback text. */
const UiFailureContext = createContext<() => void>(() => {});

/**
 * The chat chart catches its own rendering errors to show an inline message.
 * Inside a UI block the whole block falls back to text instead, so the chart
 * reports the failure to the block.
 */
function UiChart({ data, layout }: { data: unknown; layout?: unknown }) {
  const fail = useContext(UiFailureContext);
  return (
    <div className="min-w-0">
      <ChatPlotlyChart
        data={data as Record<string, unknown>[]}
        layout={(layout ?? {}) as Record<string, unknown>}
        onRenderError={fail}
      />
    </div>
  );
}

const { registry: baseRegistry } = defineRegistry(uiCatalog, {
  components: {
    Stack: ({ props, children }) => (
      <div
        className={`flex min-w-0 ${GAP_CLASS[props.gap ?? "md"]} ${
          props.direction === "horizontal"
            ? "flex-row flex-wrap [&>*]:min-w-36 [&>*]:flex-1"
            : "flex-col"
        }`}
      >
        {children}
      </div>
    ),
    Card: ({ props, children }) => (
      <section className="card card-border card-sm min-w-0 bg-base-100">
        <div className="card-body gap-3">
          {(props.title || props.description) && (
            <header>
              {props.title && <h3 className="card-title text-sm">{props.title}</h3>}
              {props.description && (
                <p className="text-xs text-base-content/60">{props.description}</p>
              )}
            </header>
          )}
          {children}
        </div>
      </section>
    ),
    Metric: ({ props }) => {
      const tone = (props.tone ?? "neutral") as Tone;
      const status = tone === "neutral" ? null : TONE_ICON[tone];
      return (
        <div className="stats min-w-0 border border-base-content/10 bg-base-100">
          <div className="stat px-4 py-3">
            {status && (
              <div className={`stat-figure ${status.text}`}>
                <status.Icon className="h-4 w-4" aria-label={status.label} role="img" />
              </div>
            )}
            <div className="stat-title text-xs whitespace-normal">{props.label}</div>
            <div className="stat-value text-xl tabular-nums break-all">
              {String(props.value)}
              {props.unit && (
                <span className="ml-1 text-sm font-normal text-base-content/60">{props.unit}</span>
              )}
            </div>
            {props.detail && (
              <div className="stat-desc whitespace-normal break-words">{props.detail}</div>
            )}
          </div>
        </div>
      );
    },
    Table: ({ props }) => (
      <div className="min-w-0 overflow-x-auto rounded-lg border border-base-content/10">
        <table className="table table-sm">
          {props.caption && (
            <caption className="caption-top px-3 pt-2 text-left text-xs text-base-content/60">
              {props.caption}
            </caption>
          )}
          <thead>
            <tr>
              {props.columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className={column.align === "right" ? "text-right" : undefined}
                >
                  {column.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {props.rows.map((row, i) => (
              <tr key={i}>
                {props.columns.map((column) => (
                  <td
                    key={column.key}
                    className={column.align === "right" ? "text-right tabular-nums" : undefined}
                  >
                    {formatCell(row[column.key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    ),
    Alert: ({ props }) => {
      const { Icon, label } = TONE_ICON[props.tone];
      return (
        <div className={`alert alert-soft ${ALERT_CLASS[props.tone]} items-start text-sm`}>
          <Icon className="mt-0.5 h-4 w-4 shrink-0" aria-label={label} role="img" />
          <div className="min-w-0 break-words">
            {props.title && <p className="font-medium">{props.title}</p>}
            <p>{props.message}</p>
          </div>
        </div>
      );
    },
    Text: ({ props }) =>
      props.variant === "heading" ? (
        <h3 className="text-sm font-semibold">{props.text}</h3>
      ) : (
        <p
          className={`text-sm whitespace-pre-wrap break-words ${
            props.variant === "muted" ? "text-base-content/60" : ""
          }`}
        >
          {props.text}
        </p>
      ),
    Chart: ({ props }) => <UiChart data={props.data} layout={props.layout} />,
    Link: ({ props }) => {
      // Validated with the spec; checked again here because this is the navigation.
      const href = safeInternalHref(props.href);
      if (!href) return <span className="text-sm">{props.label}</span>;
      return (
        <ChatLink href={href} className="link link-hover text-sm">
          {props.label}
        </ChatLink>
      );
    },
  },
});

/**
 * json-render catches an element's error itself and renders nothing in its
 * place, which would silently drop content. This boundary sits inside it and
 * tells the block instead.
 */
class ElementGuard extends Component<{ children: ReactNode }, { failed: boolean }> {
  static contextType = UiFailureContext;
  declare context: () => void;
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch() {
    this.context();
  }

  render() {
    return this.state.failed ? null : this.props.children;
  }
}

const registry: ComponentRegistry = Object.fromEntries(
  Object.entries(baseRegistry).map(([type, Render]) => [
    type,
    function Guarded(props: ComponentRenderProps) {
      return (
        <ElementGuard>
          <Render {...props} />
        </ElementGuard>
      );
    },
  ]),
);

function Fallback({ text }: { text: string }) {
  return (
    <div className="my-3">
      <p className="mb-1 text-xs text-base-content/50">This view could not be displayed.</p>
      {text && <ChatMarkdown>{text}</ChatMarkdown>}
    </div>
  );
}

/**
 * A read-only UI the assistant composed with `render_ui`. The stored spec is
 * validated against the shared catalog before json-render sees it; an unknown
 * version, an invalid spec or a rendering error shows the plain-text fallback.
 */
export const ChatUiBlock = memo(function ChatUiBlock({ ui }: { ui: unknown }) {
  const parsed = useMemo(() => parseUiBlock(ui), [ui]);
  const [failed, setFailed] = useState(false);
  const fail = useCallback(() => setFailed(true), []);
  if (parsed.status !== "ok" || failed) return <Fallback text={parsed.fallback} />;
  return (
    <div className="my-3 min-w-0" data-testid="chat-ui-block">
      <UiFailureContext.Provider value={fail}>
        {/* No state, actions or functions: the catalog is display-only. */}
        <JSONUIProvider registry={registry}>
          <Renderer spec={parsed.spec as unknown as Spec} registry={registry} />
        </JSONUIProvider>
      </UiFailureContext.Provider>
    </div>
  );
});
