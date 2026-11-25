"use client";

import { CheckCircle2, Circle, CircleDot, Coins, Flame, Lightbulb, ListChecks, Network, ShieldBan, ShieldCheck, ThermometerSun, UserCheck } from "lucide-react";

import { StatCard } from "@/components/ls/stat-card";
import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { t } from "@/i18n";
import { ago, num } from "@/lib/format";
import { platformLabel, statusMeta } from "@/lib/status";
import type { TaskDetail } from "@/lib/types";

export function OverviewTab({ task }: { task: TaskDetail }) {
  const total = task.leads.hot + task.leads.warm + task.leads.cold;
  const u = task.usage;
  const yields = Object.entries(task.platform_yield).sort((a, b) => b[1].leads - a[1].leads);
  const cov = task.coverage;

  return (
    <div className="flex flex-col gap-4 md:gap-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <StatCard label={t("Leads")} value={total} icon={UserCheck} />
        <StatCard label={t("Hot")} value={task.leads.hot} icon={Flame} tone="text-rose-600 dark:text-rose-400" />
        <StatCard label={t("Warm")} value={task.leads.warm} icon={ThermometerSun} tone="text-amber-600 dark:text-amber-400" />
        <StatCard
          label={t("Intents")}
          value={Object.values(task.intents).reduce((a, b) => a + b, 0)}
          icon={CircleDot}
          tone="text-blue-600 dark:text-blue-400"
          hint={t("{r} running · {o} open", { r: task.intents.running, o: task.intents.open })}
        />
        <StatCard label={t("Communities")} value={cov.communities_seen ?? 0} icon={Network} hint={t("{n} mined", { n: cov.communities_mined ?? 0 })} />
        <StatCard label={t("Tokens")} value={num(u.i + u.o + u.cr + u.cw)} icon={Coins} hint={t("{n} model calls", { n: u.calls })} />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>{t("Goals")}</CardTitle>
            <CardDescription>{t("Counted from verified leads; the planner can't mark a goal met early")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {task.goals.length === 0 && (
              <p className="text-muted-foreground text-sm">{t("Goals are created from the brief when the task starts.")}</p>
            )}
            {task.goals.map((g) => (
              <div key={g.id} className="space-y-2">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-muted-foreground text-xs">#{g.id}</span>
                  <span className="flex-1 text-sm">{g.text}</span>
                  <StatusBadge domain="goal" value={g.state} dot />
                </div>
                <div className="flex items-center gap-3">
                  <Progress value={Math.min(100, (g.have / Math.max(1, g.target)) * 100)} className="h-2" />
                  <span className="shrink-0 text-muted-foreground text-xs tabular-nums">
                    {g.have}/{g.target} {statusMeta("level", g.min_intent).label.toLowerCase()}+
                  </span>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ListChecks className="size-4" />
              {t("Planner's todo list")}
            </CardTitle>
            <CardDescription>{t("Kept across planning rounds")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {task.todos.length === 0 && <p className="text-muted-foreground text-sm">{t("Empty.")}</p>}
            {task.todos.map((td, i) => (
              <div key={`${i}-${td.content}`} className="flex items-start gap-2 text-sm">
                {td.status === "completed" ? (
                  <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-emerald-500" />
                ) : td.status === "in_progress" ? (
                  <CircleDot className="mt-0.5 size-4 shrink-0 text-blue-500" />
                ) : (
                  <Circle className="mt-0.5 size-4 shrink-0 text-muted-foreground" />
                )}
                <span className={td.status === "completed" ? "text-muted-foreground line-through" : undefined}>{td.content}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="gap-0 pb-0 lg:col-span-2">
          <CardHeader className="pb-4">
            <CardTitle>{t("Platform yield")}</CardTitle>
            <CardDescription>{t("Finished intents and the leads they produced; the planner concentrates where this is high")}</CardDescription>
          </CardHeader>
          <CardContent className="px-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-6">{t("Platform")}</TableHead>
                  <TableHead className="text-right">{t("Intents")}</TableHead>
                  <TableHead className="text-right">{t("Leads")}</TableHead>
                  <TableHead className="pr-6 text-right">{t("Leads / intent")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {yields.length === 0 && (
                  <TableRow>
                    <TableCell colSpan={4} className="py-6 text-center text-muted-foreground">
                      {t("No finished intents yet.")}
                    </TableCell>
                  </TableRow>
                )}
                {yields.map(([p, y]) => (
                  <TableRow key={p}>
                    <TableCell className="pl-6">{platformLabel(p)}</TableCell>
                    <TableCell className="text-right tabular-nums">{y.intents}</TableCell>
                    <TableCell className="text-right tabular-nums">{y.leads}</TableCell>
                    <TableCell className="pr-6 text-right tabular-nums">{(y.leads / Math.max(1, y.intents)).toFixed(1)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>

        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle>{t("Constraints")}</CardTitle>
              <CardDescription>{t("Extracted from the brief")}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {task.constraints.length === 0 && <p className="text-muted-foreground text-sm">{t("None.")}</p>}
              {task.constraints.map((c, i) => (
                <div key={`${i}-${c.text}`} className="flex items-start gap-2 text-sm">
                  {c.kind === "allow" ? (
                    <ShieldCheck className="mt-0.5 size-4 shrink-0 text-emerald-500" />
                  ) : (
                    <ShieldBan className="mt-0.5 size-4 shrink-0 text-red-500" />
                  )}
                  {c.text}
                </div>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>{t("Operator hints")}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2">
              {task.hints.length === 0 && (
                <p className="text-muted-foreground text-sm">{t("Send hints from the Sessions tab to steer the planner.")}</p>
              )}
              {task.hints.map((h) => (
                <div key={h.id} className="flex items-start gap-2 text-sm">
                  <Lightbulb className="mt-0.5 size-4 shrink-0 text-violet-500" />
                  <span className="flex-1">{h.text}</span>
                  <span className="shrink-0 text-muted-foreground text-xs">{ago(h.created_at)}</span>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
