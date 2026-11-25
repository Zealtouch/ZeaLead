"use client";

import { useState } from "react";

import Link from "next/link";

import { Coins, Flame, Handshake, Target, ThermometerSun, UserCheck, Wrench } from "lucide-react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import { ExtLink } from "@/components/ls/ext-link";
import { LeadSheet } from "@/components/ls/lead-sheet";
import { Loading } from "@/components/ls/loading";
import { PageHeader } from "@/components/ls/page-header";
import { StatCard } from "@/components/ls/stat-card";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { type ChartConfig, ChartContainer, ChartTooltip, ChartTooltipContent } from "@/components/ui/chart";
import { usePoll } from "@/hooks/use-poll";
import { t } from "@/i18n";
import { api } from "@/lib/api";
import { ago, num } from "@/lib/format";
import { platformLabel } from "@/lib/status";
import { useActiveCompany } from "@/stores/company/company-store";

const leadConfig = {
  hot: { label: t("Hot"), color: "hsl(347 77% 50%)" },
  warm: { label: t("Warm"), color: "hsl(38 92% 50%)" },
  cold: { label: t("Cold"), color: "hsl(215 16% 57%)" },
} satisfies ChartConfig;

const tokenConfig = {
  tokens: { label: t("Tokens"), color: "hsl(263 70% 60%)" },
} satisfies ChartConfig;

function shortDate(d: string) {
  return d.slice(5);
}

export default function DashboardPage() {
  const company = useActiveCompany();
  const { data, loading } = usePoll(() => api.dashboard({ company }), [company], 10000);
  const [openLead, setOpenLead] = useState<number | null>(null);

  if (loading && !data) return <Loading className="min-h-96" />;
  if (!data) return null;

  const l = data.leads;
  const tasksTotal = Object.values(data.tasks).reduce((a, b) => a + b, 0);
  const tokensTotal = data.tokens.i + data.tokens.o + data.tokens.cr + data.tokens.cw;
  const platforms = Object.entries(l.platforms).sort((a, b) => b[1] - a[1]);
  const maxPlat = Math.max(1, ...platforms.map(([, v]) => v));
  const series = data.series.map((s) => ({ ...s, date: shortDate(s.date) }));

  return (
    <div className="flex flex-1 flex-col gap-4 md:gap-6">
      <PageHeader
        title={t("Dashboard")}
        description={t("Leads found across every task, what's running now, and what it costs")}
        actions={
          <Button size="sm" asChild>
            <Link prefetch={false} href="/function/tasks?new=1">
              <Target />
              {t("New task")}
            </Link>
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <StatCard label={t("Leads")} value={l.total} icon={UserCheck} />
        <StatCard label={t("Hot")} value={l.hot} icon={Flame} tone="text-rose-600 dark:text-rose-400" />
        <StatCard label={t("Warm")} value={l.warm} icon={ThermometerSun} tone="text-amber-600 dark:text-amber-400" />
        <StatCard
          label={t("Won")}
          value={l.won}
          icon={Handshake}
          tone="text-emerald-600 dark:text-emerald-400"
          hint={t("{n} contacted · {r} replied", { n: l.contacted, r: l.replied })}
        />
        <StatCard
          label={t("Tasks")}
          value={tasksTotal}
          icon={Target}
          tone="text-blue-600 dark:text-blue-400"
          hint={t("{n} running now", { n: data.running.length })}
        />
        <StatCard
          label={t("Tokens")}
          value={num(tokensTotal)}
          icon={Coins}
          hint={t("{n} model calls", { n: num(data.tokens.calls) })}
        />
      </div>

      {data.running.length > 0 && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-blue-500/30 bg-blue-500/5 px-4 py-2.5 text-sm">
          <span className="relative flex size-2">
            <span className="absolute inline-flex size-full animate-ping rounded-full bg-blue-400 opacity-70" />
            <span className="relative inline-flex size-2 rounded-full bg-blue-500" />
          </span>
          <span className="font-medium">{t("Running now:")}</span>
          {data.running.map((r) => (
            <Link
              key={r.id}
              prefetch={false}
              href={`/function/tasks/detail?id=${r.id}`}
              className="rounded-md bg-background px-2 py-0.5 hover:underline"
            >
              {r.name}
            </Link>
          ))}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>{t("Leads per day")}</CardTitle>
            <CardDescription>{t("Last 14 days, by buying intent")}</CardDescription>
          </CardHeader>
          <CardContent>
            <ChartContainer config={leadConfig} className="h-[220px] w-full">
              <BarChart data={series} margin={{ top: 4, right: 4, bottom: 0, left: 0 }} maxBarSize={36}>
                <CartesianGrid vertical={false} />
                <XAxis dataKey="date" tickLine={false} axisLine={false} tick={{ fontSize: 10 }} tickMargin={6} />
                <YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fontSize: 10 }} width={28} />
                <ChartTooltip cursor={false} content={<ChartTooltipContent indicator="line" />} />
                <Bar dataKey="cold" stackId="1" fill="var(--color-cold)" />
                <Bar dataKey="warm" stackId="1" fill="var(--color-warm)" />
                <Bar dataKey="hot" stackId="1" fill="var(--color-hot)" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ChartContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t("Where leads come from")}</CardTitle>
            <CardDescription>{t("Leads per platform")}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {platforms.length === 0 && <p className="text-muted-foreground text-sm">{t("No leads yet.")}</p>}
            {platforms.map(([p, v]) => (
              <div key={p} className="space-y-1">
                <div className="flex justify-between text-sm">
                  <span>{platformLabel(p)}</span>
                  <span className="font-medium tabular-nums">{v}</span>
                </div>
                <div className="h-2 overflow-hidden rounded-full bg-muted">
                  <div className="h-full rounded-full bg-primary" style={{ width: `${(v / maxPlat) * 100}%` }} />
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>{t("Newest leads")}</CardTitle>
            <CardDescription>
              <Link prefetch={false} href="/function/leads" className="hover:underline">
                {t("See all leads →")}
              </Link>
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-1 px-2">
            {data.recent_leads.length === 0 && (
              <p className="px-2 text-muted-foreground text-sm">{t("Leads appear here as tasks find them.")}</p>
            )}
            {data.recent_leads.map((ld) => (
              <button
                key={ld.node_id}
                type="button"
                onClick={() => setOpenLead(ld.node_id)}
                className="flex w-full items-start gap-3 rounded-lg px-2 py-2 text-left hover:bg-muted/60"
              >
                <StatusBadge domain="level" value={ld.intent_level} dot className="mt-0.5" />
                <div className="min-w-0 flex-1">
                  <div className="line-clamp-1 font-medium text-sm">{ld.pain || ld.quote}</div>
                  <div className="line-clamp-1 text-muted-foreground text-xs">
                    {ld.author} · {platformLabel(ld.platform)} · {ld.campaign_name}
                  </div>
                </div>
                <span className="shrink-0 text-muted-foreground text-xs">{ago(ld.created_at)}</span>
              </button>
            ))}
          </CardContent>
        </Card>

        <div className="flex flex-col gap-4">
          <Card>
            <CardHeader>
              <CardTitle>{t("Top communities")}</CardTitle>
              <CardDescription>{t("Where buyers talk most")}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {data.top_communities.length === 0 && <p className="text-muted-foreground text-sm">{t("None yet.")}</p>}
              {data.top_communities.map((c) => (
                <div key={`${c.platform}-${c.key}`} className="flex items-center gap-2 text-sm">
                  <Badge variant="outline" className="text-[10px]">
                    {platformLabel(c.platform)}
                  </Badge>
                  <ExtLink href={c.url} className="min-w-0 flex-1 text-foreground" icon={false}>
                    {c.key}
                  </ExtLink>
                  <span className="font-medium tabular-nums">{c.leads}</span>
                </div>
              ))}
            </CardContent>
          </Card>
          <Card>
            <CardHeader>
              <CardTitle>{t("Token spend")}</CardTitle>
              <CardDescription>
                <span className="inline-flex items-center gap-1">
                  <Wrench className="size-3" />
                  {t("{n} tool calls, {e} failed", { n: num(data.tool_calls.total), e: data.tool_calls.errors })}
                </span>
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ChartContainer config={tokenConfig} className="h-[110px] w-full">
                <BarChart data={series} margin={{ top: 4, right: 0, bottom: 0, left: 0 }} maxBarSize={18}>
                  <XAxis dataKey="date" hide />
                  <ChartTooltip
                    cursor={false}
                    content={<ChartTooltipContent indicator="line" formatter={(v) => num(Number(v))} />}
                  />
                  <Bar dataKey="tokens" fill="var(--color-tokens)" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ChartContainer>
            </CardContent>
          </Card>
        </div>
      </div>

      <LeadSheet leadId={openLead} onOpenChange={(o) => !o && setOpenLead(null)} />
    </div>
  );
}
