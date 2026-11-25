"use client";

import * as React from "react";

import { AlertTriangle, Brain, ChevronRight, FileText, Wrench } from "lucide-react";

import { Markdown } from "@/components/markdown";
import { t } from "@/i18n";
import { fmtTime, pretty } from "@/lib/format";
import type { Block, RunMessage } from "@/lib/types";
import { cn } from "@/lib/utils";

function Collapsible({
  title,
  icon: Icon,
  tone,
  children,
  defaultOpen = false,
  meta,
}: {
  title: React.ReactNode;
  icon: React.ElementType;
  tone?: "error" | "muted";
  children: React.ReactNode;
  defaultOpen?: boolean;
  meta?: React.ReactNode;
}) {
  const [open, setOpen] = React.useState(defaultOpen);
  return (
    <div
      className={cn(
        "rounded-lg border text-sm",
        tone === "error" ? "border-red-500/30 bg-red-500/5" : "bg-muted/30",
      )}
    >
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left"
        aria-expanded={open}
      >
        <ChevronRight className={cn("size-3.5 shrink-0 text-muted-foreground transition-transform", open && "rotate-90")} />
        <Icon className={cn("size-3.5 shrink-0", tone === "error" ? "text-red-500" : "text-muted-foreground")} />
        <span className="min-w-0 flex-1 truncate">{title}</span>
        {meta}
      </button>
      {open && <div className="border-t px-3 py-2">{children}</div>}
    </div>
  );
}

function Pre({ text }: { text: string }) {
  return (
    <pre className="max-h-96 overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-relaxed text-foreground/80">
      {text}
    </pre>
  );
}

function inputPreview(input: Record<string, unknown>): string {
  const s = JSON.stringify(input);
  return s.length > 110 ? `${s.slice(0, 110)}…` : s;
}

// Transcript of one agent session. Model text is rendered as Markdown (react-markdown never
// renders raw HTML); tool inputs and results, which carry text from collected posts, are shown
// as plain preformatted text. Each tool result is shown under the call that produced it.
export function Transcript({ messages }: { messages: RunMessage[] }) {
  const results = React.useMemo(() => {
    const m = new Map<string, Extract<Block, { type: "tool_result" }>>();
    for (const msg of messages)
      if (msg.role === "tool")
        for (const b of msg.content) if (b.type === "tool_result") m.set(b.tool_use_id, b);
    return m;
  }, [messages]);

  return (
    <div className="flex flex-col gap-3">
      {messages.map((msg, idx) => {
        if (msg.role === "tool") return null;
        if (msg.role === "user") {
          const text = msg.content.map((b) => (b.type === "text" ? b.text : "")).join("\n");
          return (
            <Collapsible
              key={msg.id}
              icon={FileText}
              title={idx === 0 ? t("Prompt and situation given to the agent") : t("Runtime note")}
              meta={<span className="text-muted-foreground text-xs tabular-nums">{fmtTime(msg.ts)}</span>}
            >
              <Pre text={text} />
            </Collapsible>
          );
        }
        return (
          <div key={msg.id} className="flex flex-col gap-2">
            {msg.content.map((b, i) => {
              const key = `${msg.id}-${i}`;
              if (b.type === "text")
                return (
                  <div key={key} className="rounded-xl bg-muted/60 px-4 py-3">
                    <Markdown text={b.text} />
                  </div>
                );
              if (b.type === "thinking")
                return (
                  <Collapsible key={key} icon={Brain} title={t("Thinking")}>
                    <p className="whitespace-pre-wrap text-muted-foreground text-xs">{b.text}</p>
                  </Collapsible>
                );
              if (b.type === "tool_use") {
                const r = results.get(b.id);
                return (
                  <Collapsible
                    key={key}
                    icon={r?.is_error ? AlertTriangle : Wrench}
                    tone={r?.is_error ? "error" : undefined}
                    title={
                      <span>
                        <span className="font-medium font-mono text-xs">{b.name}</span>{" "}
                        <span className="font-mono text-muted-foreground text-xs">{inputPreview(b.input)}</span>
                      </span>
                    }
                    meta={
                      !r ? (
                        <span className="text-blue-600 text-xs dark:text-blue-400">{t("running…")}</span>
                      ) : r.is_error ? (
                        <span className="text-red-600 text-xs dark:text-red-400">{t("error")}</span>
                      ) : null
                    }
                  >
                    <div className="space-y-2">
                      <div className="text-muted-foreground text-xs">{t("Input")}</div>
                      <Pre text={pretty(b.input)} />
                      {r && (
                        <>
                          <div className="text-muted-foreground text-xs">{t("Result")}</div>
                          <Pre text={r.content} />
                        </>
                      )}
                    </div>
                  </Collapsible>
                );
              }
              return null;
            })}
            <span className="self-end text-muted-foreground text-[11px] tabular-nums">{fmtTime(msg.ts)}</span>
          </div>
        );
      })}
    </div>
  );
}
