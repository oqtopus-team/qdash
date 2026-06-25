"use client";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";

// BlockNote side: reuse the EXACT component already running in cryo wiring.
// That reuse is itself a finding — the forum can share one editor stack.
const WiringBlockEditor = dynamic(
  () =>
    import("@/components/features/cryo/WiringBlockEditor").then((m) => ({
      default: m.WiringBlockEditor,
    })),
  { ssr: false },
);

const TiptapEditor = dynamic(
  () =>
    import("@/components/features/editor-compare/TiptapEditor").then((m) => ({
      default: m.TiptapEditor,
    })),
  { ssr: false },
);

const BLOCKNOTE_SAMPLE_MARKDOWN = `# BlockNote デモ

これは **BlockNote** エディタです。\`/\` を打つとスラッシュメニューが出ます（テーブル・画像・見出し・リスト・トグル・コード等）。行頭の ⠿ ハンドルでドラッグ並べ替えもできます。

| 機能 | このデモでの状態 |
| --- | --- |
| テーブル | GUI で挿入・列幅調整あり |
| 画像リサイズ | ドラッグでリサイズ可（previewWidth） |

画像は \`⌘/Ctrl+V\` で貼り付けると base64 として取り込まれます。`;

/** Mirror cryo's theme detection so BlockNote matches the daisyUI theme. */
function useThemeScheme(): "light" | "dark" {
  const [scheme, setScheme] = useState<"light" | "dark">("light");
  useEffect(() => {
    const compute = () => {
      const t = document.documentElement.getAttribute("data-theme")?.toLowerCase() ?? "";
      const dark = ["dark", "night", "dracula", "dim", "abyss", "dev-dark"];
      setScheme(dark.includes(t) ? "dark" : "light");
    };
    compute();
    const obs = new MutationObserver(compute);
    obs.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => obs.disconnect();
  }, []);
  return scheme;
}

type BlockNoteView = "json" | "markdown";
type TiptapView = "json" | "html";

export default function EditorComparePage() {
  const colorScheme = useThemeScheme();

  const [bnBlocks, setBnBlocks] = useState<Record<string, unknown>[]>([]);
  const [bnMarkdown, setBnMarkdown] = useState("");
  const [bnView, setBnView] = useState<BlockNoteView>("json");

  const [ttJson, setTtJson] = useState<unknown>(null);
  const [ttHtml, setTtHtml] = useState("");
  const [ttView, setTtView] = useState<TiptapView>("json");

  return (
    <div className="p-4 max-w-[1600px] mx-auto">
      <header className="mb-4">
        <h1 className="text-xl font-bold">エディタ比較: BlockNote vs Tiptap</h1>
        <p className="text-sm text-base-content/70 mt-1">
          Issue #1100 の評価用テストページ。保存はしません（ローカル state
          のみ）。両方のエディタを実際に触り、 下部パネルで{" "}
          <span className="font-mono">保存されるデータ形式</span> を見比べられます。詳細な比較は{" "}
          <span className="font-mono">yugo/issues/1100/blocknote-vs-tiptap.md</span> を参照。
        </p>
        <div className="mt-2 text-xs text-base-content/60 rounded-md border border-base-300 bg-base-200/40 p-2">
          <span className="font-semibold">見るべきポイント:</span> ① BlockNote は{" "}
          <span className="font-mono">/</span>
          メニュー・ドラッグハンドル・テーブル UI・画像リサイズが<strong>最初から付く</strong>。②
          Tiptap はツールバーも CSS も<strong>このリポジトリ内で手書き</strong>（ヘッドレス）。③
          保存データは
          <strong>どちらも JSON</strong>（マークダウン/HTML は派生）。
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* ───────────── BlockNote ───────────── */}
        <section className="rounded-lg border border-base-300 bg-base-100 overflow-hidden flex flex-col">
          <div className="flex items-center justify-between px-3 py-2 border-b border-base-300 bg-base-200/40">
            <h2 className="font-semibold">
              BlockNote{" "}
              <span className="text-xs text-base-content/50">(@blocknote ^0.51 / cryo と同一)</span>
            </h2>
            <span className="badge badge-success badge-sm">batteries-included</span>
          </div>

          <div className="p-2 min-h-[320px]">
            <WiringBlockEditor
              initialBlocks={undefined}
              legacyMarkdown={BLOCKNOTE_SAMPLE_MARKDOWN}
              editable
              colorScheme={colorScheme}
              onChange={(blocks, markdown) => {
                setBnBlocks(blocks);
                setBnMarkdown(markdown);
              }}
            />
          </div>

          <OutputPanel
            tabs={[
              { key: "json", label: "保存JSON (source of truth)" },
              { key: "markdown", label: "lossy Markdown (派生)" },
            ]}
            active={bnView}
            onSelect={(k) => setBnView(k as BlockNoteView)}
            content={
              bnView === "json" ? JSON.stringify(bnBlocks, null, 2) : bnMarkdown || "(まだ変更なし)"
            }
          />
        </section>

        {/* ───────────── Tiptap ───────────── */}
        <section className="rounded-lg border border-base-300 bg-base-100 overflow-hidden flex flex-col">
          <div className="flex items-center justify-between px-3 py-2 border-b border-base-300 bg-base-200/40">
            <h2 className="font-semibold">
              Tiptap{" "}
              <span className="text-xs text-base-content/50">(@tiptap ^3.27 / 新規・手組み)</span>
            </h2>
            <span className="badge badge-warning badge-sm">headless (UI自前)</span>
          </div>

          <div className="p-2 min-h-[320px]">
            <TiptapEditor
              onChange={(json, html) => {
                setTtJson(json);
                setTtHtml(html);
              }}
            />
          </div>

          <OutputPanel
            tabs={[
              { key: "json", label: "保存JSON (ProseMirror)" },
              { key: "html", label: "HTML (派生)" },
            ]}
            active={ttView}
            onSelect={(k) => setTtView(k as TiptapView)}
            content={
              ttView === "json"
                ? ttJson
                  ? JSON.stringify(ttJson, null, 2)
                  : "(まだ変更なし)"
                : ttHtml || "(まだ変更なし)"
            }
          />
        </section>
      </div>
    </div>
  );
}

function OutputPanel({
  tabs,
  active,
  onSelect,
  content,
}: {
  tabs: { key: string; label: string }[];
  active: string;
  onSelect: (key: string) => void;
  content: string;
}) {
  return (
    <div className="border-t border-base-300 mt-auto">
      <div className="flex gap-1 px-2 pt-2">
        {tabs.map((t) => (
          <button
            key={t.key}
            type="button"
            className={`btn btn-xs ${active === t.key ? "btn-primary" : "btn-ghost"}`}
            onClick={() => onSelect(t.key)}
          >
            {t.label}
          </button>
        ))}
      </div>
      <pre className="text-[11px] leading-tight p-3 max-h-72 overflow-auto whitespace-pre-wrap break-all bg-base-200/30 m-2 rounded">
        {content}
      </pre>
    </div>
  );
}
