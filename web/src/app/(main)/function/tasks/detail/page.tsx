"use client";

import { Suspense } from "react";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { ArrowLeft, Building2, FileDown, Pause, Play } from "lucide-react";
import { toast } from "sonner";

import { ToolCallsView } from "@/components/ls/tool-calls-view";
import { Loading } from "@/components/ls/loading";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { usePoll } from "@/hooks/use-poll";
import { t } from "@/i18n";
import { api } from "@/lib/api";
import { num } from "@/lib/format";

import { BriefTab } from "./_tabs/brief-tab";
import { CommunitiesTab } from "./_tabs/communities-tab";
import { GraphTab } from "./_tabs/graph-tab";
import { IntentsTab } from "./_tabs/intents-tab";
import { LeadsTab } from "./_tabs/leads-tab";
import { OverviewTab } from "./_tabs/overview-tab";
import { SessionsTab } from "./_tabs/sessions-tab";

const TABS = [
  ["sessions", "Sessions"],
  ["overview", "Overview"],
  ["graph", "Exploration graph"],
  ["intents", "Intents"],
  ["leads", "Leads"],
  ["communities", "Communities"],
  ["tools", "Tool calls"],
  ["brief", "Brief"],
] as const;

function TaskDetailPage() {
  const params = useSearchParams();
  const router = useRouter();
  const id = Number(params.get("id"));
  const tab = params.get("tab") ?? "sessions";
  const runParam = params.get("run");
  const run = runParam ? Number(runParam) : null;
  const { data: task, error, reload } = usePoll(() => api.task(id), [id], 4000);

  const nav = (next: Record<string, string | null>) => {
    const p = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(next)) {
      if (v === null) p.delete(k);
      else p.set(k, v);
    }
    router.replace(`/function/tasks/detail?${p.toString()}`, { scroll: false });
  };
  const openSession = (rid: number) => nav({ tab: "sessions", run: String(rid) });

  async function act(p: Promise<unknown>, ok: string) {
    try {
      await p;
      toast.success(ok);
      reload();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  if (!id) return <p className="p-6 text-muted-foreground">{t("No task selected.")}</p>;
  if (!task) return error ? <p className="p-6 text-destructive">{error}</p> : <Loading className="min-h-96" />;

  const running = task.status === "running";
  const total = task.leads.hot + task.leads.warm + task.leads.cold;

  return (
    <div className="flex flex-col gap-4 p-4 md:p-6">
      <div className="flex flex-wrap items-center gap-3">
        <Button variant="ghost" size="icon-sm" asChild aria-label={t("Back to tasks")}>
          <Link prefetch={false} href="/function/tasks">
            <ArrowLeft />
          </Link>
        </Button>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="truncate font-semibold text-xl tracking-tight">{task.name}</h1>
            <StatusBadge domain="task" value={task.status} dot />
            <span className="font-mono text-muted-foreground text-xs">t-{task.id}</span>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-muted-foreground text-sm">
            {task.company_name && (
              <span className="flex items-center gap-1">
                <Building2 className="size-3.5" />
                {task.company_name}
              </span>
            )}
            <span className="line-clamp-1 max-w-xl">{task.brief.objective || task.brief.product}</span>
            <Badge variant="outline" className="tabular-nums">
              {t("{n} leads", { n: total })}
            </Badge>
            <Badge variant="outline" className="tabular-nums">
              {t("{n} tokens", { n: num(task.tokens) })}
            </Badge>
            {task.end_reason && !running && <span className="text-xs">· {task.end_reason}</span>}
          </div>
        </div>
        <div className="ml-auto flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            onClick={() => api.downloadReport(task.id).catch((e) => toast.error((e as Error).message))}
          >
            <FileDown />
            {t("Report")}
          </Button>
          {running ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => act(api.pauseTask(task.id), t("Pausing — workers finish their current step"))}
            >
              <Pause />
              {t("Pause")}
            </Button>
          ) : (
            <Button size="sm" onClick={() => act(api.startTask(task.id), t("Task started"))} disabled={task.status === "done"}>
              <Play />
              {task.status === "created" ? t("Start") : t("Resume")}
            </Button>
          )}
        </div>
      </div>

      <Tabs value={tab} onValueChange={(v) => nav({ tab: v, run: v === "sessions" ? runParam : null })}>
        <TabsList className="flex-wrap">
          {TABS.map(([k, label]) => (
            <TabsTrigger key={k} value={k}>
              {t(label)}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="sessions" className="mt-2">
          <SessionsTab task={task} initialRun={run} onRunChange={(rid) => nav({ run: String(rid) })} />
        </TabsContent>
        <TabsContent value="overview" className="mt-2">
          <OverviewTab task={task} />
        </TabsContent>
        <TabsContent value="graph" className="mt-2">
          {tab === "graph" && <GraphTab task={task} onOpenSession={openSession} />}
        </TabsContent>
        <TabsContent value="intents" className="mt-2">
          {tab === "intents" && <IntentsTab task={task} onOpenSession={openSession} />}
        </TabsContent>
        <TabsContent value="leads" className="mt-2">
          {tab === "leads" && <LeadsTab task={task} />}
        </TabsContent>
        <TabsContent value="communities" className="mt-2">
          {tab === "communities" && <CommunitiesTab task={task} />}
        </TabsContent>
        <TabsContent value="tools" className="mt-2">
          {tab === "tools" && <ToolCallsView campaign={task.id} />}
        </TabsContent>
        <TabsContent value="brief" className="mt-2">
          {tab === "brief" && <BriefTab task={task} onSaved={reload} />}
        </TabsContent>
      </Tabs>
    </div>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<Loading className="min-h-96" />}>
      <TaskDetailPage />
    </Suspense>
  );
}
