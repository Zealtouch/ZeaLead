"use client";

import * as React from "react";

import { ArrowUp, CheckCircle2, CircleDashed, Clock, Compass, Lightbulb, PenLine, Radio, Target, XCircle } from "lucide-react";
import { toast } from "sonner";

import { Loading } from "@/components/ls/loading";
import { Transcript } from "@/components/ls/transcript";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { usePoll } from "@/hooks/use-poll";
import { t } from "@/i18n";
import { api } from "@/lib/api";
import { duration, num } from "@/lib/format";
import { setVisibleInterval } from "@/lib/polling";
import type { Run, RunMessage, TaskDetail } from "@/lib/types";
import { cn } from "@/lib/utils";

function RunIcon({ state }: { state: Run["state"] }) {
  if (state === "running") return <CircleDashed className="size-4 shrink-0 animate-spin text-blue-500 [animation-duration:3s]" />;
  if (state === "error") return <XCircle className="size-4 shrink-0 text-red-500" />;
  if (state === "exhausted" || state === "stopped") return <Clock className="size-4 shrink-0 text-violet-500" />;
  return <CheckCircle2 className="size-4 shrink-0 text-emerald-500" />;
}

function Group({ icon: Icon, label, children }: { icon: React.ElementType; label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-0.5">
      <div className="flex items-center gap-2 px-2 pt-3 pb-1 text-muted-foreground text-xs">
        <Icon className="size-3.5" />
        {label}
      </div>
      {children}
    </div>
  );
}

function RunRow({ r, selected, onClick, label }: { r: Run; selected: boolean; onClick: () => void; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm",
        selected ? "bg-muted font-medium" : "hover:bg-muted/60",
      )}
    >
      <RunIcon state={r.state} />
      {r.intent_id && <span className="shrink-0 font-mono text-muted-foreground text-[10px]">#{r.intent_id}</span>}
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {r.state === "running" && (
        <Badge variant="outline" className="h-4 shrink-0 border-blue-500/30 px-1 text-[10px] text-blue-600 dark:text-blue-400">
          {t("Live")}
        </Badge>
      )}
    </button>
  );
}

// Sessions: the live monitor. Left, every agent session of the task; right, the selected
// session's transcript, appended every 2 s while it runs; bottom, a hint box to steer the planner.
export function SessionsTab({
  task,
  initialRun,
  onRunChange,
}: {
  task: TaskDetail;
  initialRun?: number | null;
  onRunChange?: (id: number) => void;
}) {
  const { data } = usePoll(() => api.sessions(task.id), [task.id], 3000);
  const [selected, setSelected] = React.useState<number | null>(initialRun ?? null);
  const [messages, setMessages] = React.useState<RunMessage[]>([]);
  const [run, setRun] = React.useState<Run | null>(null);
  const [hint, setHint] = React.useState("");
  const [sending, setSending] = React.useState(false);
  const bottomRef = React.useRef<HTMLDivElement>(null);
  const stickRef = React.useRef(true);

  const runs = data?.runs ?? [];
  const planner = runs.filter((r) => r.role === "planner").reverse();
  const workers = runs.filter((r) => r.role === "worker").reverse();
  const decomposer = runs.filter((r) => r.role === "decomposer");
  const writers = runs.filter((r) => r.role === "writer").reverse();

  // Default selection: a live worker, else the newest session.
  React.useEffect(() => {
    if (selected !== null || !runs.length) return;
    const live = runs.filter((r) => r.state === "running" && r.role === "worker").at(-1);
    setSelected((live ?? runs.at(-1))?.id ?? null);
  }, [runs, selected]);

  React.useEffect(() => {
    if (initialRun) setSelected(initialRun);
  }, [initialRun]);

  // Load the transcript; while the session runs, fetch only messages after the last one seen.
  React.useEffect(() => {
    if (selected === null) return;
    let live = true;
    let last = 0;
    setMessages([]);
    setRun(null);
    stickRef.current = true;
    const load = async () => {
      const r = await api.runMessages(selected, last);
      if (!live) return;
      setRun(r.run);
      if (r.messages.length) {
        last = r.messages[r.messages.length - 1].id;
        setMessages((m) => [...m, ...r.messages]);
      }
      return r.run.state;
    };
    let stop: (() => void) | undefined;
    load()
      .then((state) => {
        if (live && state === "running") stop = setVisibleInterval(load, 2000);
      })
      .catch((e) => toast.error((e as Error).message));
    return () => {
      live = false;
      stop?.();
    };
  }, [selected]);

  React.useEffect(() => {
    void messages.length;
    if (stickRef.current) bottomRef.current?.scrollIntoView({ block: "end" });
  }, [messages.length]);

  const select = (id: number) => {
    setSelected(id);
    onRunChange?.(id);
  };

  async function sendHint() {
    const text = hint.trim();
    if (!text) return;
    setSending(true);
    try {
      await api.addHint(task.id, text);
      setHint("");
      toast.success(
        data?.running ? t("Hint sent — the planner reads it on its next round") : t("Hint saved — the planner reads it when the task resumes"),
      );
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSending(false);
    }
  }

  if (!data) return <Loading className="min-h-96" />;
  const u = data.usage;

  return (
    <div className="grid h-[calc(100dvh-10.5rem)] min-h-[520px] gap-4 lg:grid-cols-[320px_1fr]">
      <Card className="flex min-h-0 flex-col gap-0 py-0">
        <div className="border-b px-3 py-3">
          <div className="font-medium text-muted-foreground text-xs">{t("Sessions")}</div>
          <div className="mt-1 flex flex-wrap items-center gap-1.5 text-muted-foreground text-xs">
            <span>{t("In")}</span>
            <Badge variant="secondary" className="tabular-nums">
              {num(u.i)}
            </Badge>
            <span>{t("Cache")}</span>
            <Badge variant="secondary" className="tabular-nums">
              {num(u.cr)}
            </Badge>
            <span>{t("Out")}</span>
            <Badge variant="secondary" className="tabular-nums">
              {num(u.o)}
            </Badge>
          </div>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto px-1.5 pb-3">
          {!runs.length && (
            <p className="px-3 py-6 text-center text-muted-foreground text-sm">
              {t("No sessions yet. Start the task to watch the agents work.")}
            </p>
          )}
          {decomposer.length > 0 && (
            <Group icon={Target} label={t("Goal decomposer")}>
              {decomposer.map((r) => (
                <RunRow key={r.id} r={r} selected={r.id === selected} onClick={() => select(r.id)} label={t("Brief → goals")} />
              ))}
            </Group>
          )}
          {planner.length > 0 && (
            <Group icon={Compass} label={t("Planner · {n} rounds", { n: planner.length })}>
              {planner.map((r, i) => (
                <RunRow
                  key={r.id}
                  r={r}
                  selected={r.id === selected}
                  onClick={() => select(r.id)}
                  label={`${t("Round {n}", { n: planner.length - i })} · ${
                    (r.title ?? "").replace(/^Planning round\s*/, "").replace(/^\((.*)\)$/, "$1").trim() || t("situational analysis")
                  }`}
                />
              ))}
            </Group>
          )}
          {workers.length > 0 && (
            <Group icon={Radio} label={t("Workers · {n}", { n: workers.length })}>
              {workers.map((r) => (
                <RunRow key={r.id} r={r} selected={r.id === selected} onClick={() => select(r.id)} label={r.title ?? ""} />
              ))}
            </Group>
          )}
          {writers.length > 0 && (
            <Group icon={PenLine} label={t("Message writer · {n}", { n: writers.length })}>
              {writers.map((r) => (
                <RunRow
                  key={r.id}
                  r={r}
                  selected={r.id === selected}
                  onClick={() => select(r.id)}
                  label={(r.title ?? "").replace(/^Messages for /, "")}
                />
              ))}
            </Group>
          )}
        </div>
      </Card>

      <Card className="flex min-h-0 flex-col gap-0 py-0">
        <div className="flex flex-wrap items-center gap-2 border-b px-4 py-3">
          {run ? (
            <>
              <span className="font-medium text-sm capitalize">
                {run.role} · {t("Session #{id}", { id: run.id })}
              </span>
              <Badge variant="outline">{run.model}</Badge>
              <StatusBadge domain="run" value={run.state} dot />
              <span className="ml-auto flex items-center gap-3 text-muted-foreground text-xs">
                <span className="flex items-center gap-1">
                  <Clock className="size-3.5" />
                  {duration((run.ended_at ?? Date.now() / 1000) - run.started_at)}
                </span>
                <span className="tabular-nums">
                  {num(run.input_tokens)} in · {num(run.output_tokens)} out · {run.tool_calls} {t("tools")}
                </span>
              </span>
            </>
          ) : (
            <span className="text-muted-foreground text-sm">{t("Select a session")}</span>
          )}
        </div>
        <div
          className="min-h-0 flex-1 overflow-y-auto px-4 py-4"
          onScroll={(e) => {
            const el = e.currentTarget;
            stickRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
          }}
        >
          {run?.title && run.role === "worker" && (
            <p className="mb-3 rounded-lg border border-blue-500/20 bg-blue-500/5 px-3 py-2 text-sm">
              <span className="font-medium">{t("Intent:")}</span> {run.title}
            </p>
          )}
          {run?.error && (
            <p className="mb-3 rounded-lg border border-red-500/30 bg-red-500/5 px-3 py-2 text-red-600 text-sm dark:text-red-400">
              {run.error}
            </p>
          )}
          {selected !== null && !run ? <Loading /> : <Transcript messages={messages} />}
          <div ref={bottomRef} />
        </div>
        <div className="border-t p-3">
          <div className="rounded-xl border bg-muted/30 p-2">
            <Textarea
              value={hint}
              onChange={(e) => setHint(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) void sendHint();
              }}
              placeholder={t("Steer the planner — e.g. “focus on agency owners posting on LinkedIn” (⌘/Ctrl+Enter to send)")}
              rows={2}
              className="resize-none border-0 bg-transparent shadow-none focus-visible:ring-0"
            />
            <div className="flex items-center justify-between px-1">
              <span className="flex items-center gap-1 text-muted-foreground text-xs">
                <Lightbulb className="size-3.5" />
                {t("{n} hints given", { n: task.hints.length })}
              </span>
              <Button size="icon-sm" onClick={sendHint} disabled={sending || !hint.trim()} aria-label={t("Send hint")}>
                <ArrowUp />
              </Button>
            </div>
          </div>
        </div>
      </Card>
    </div>
  );
}
