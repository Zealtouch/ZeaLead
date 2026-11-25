"use client";

import { useState } from "react";

import Link from "next/link";

import { ArrowDownToLine, ArrowUpFromLine, Coins, DatabaseZap, MessagesSquare } from "lucide-react";

import { EmptyRow, Loading } from "@/components/ls/loading";
import { PageHeader } from "@/components/ls/page-header";
import { StatCard } from "@/components/ls/stat-card";
import { Transcript } from "@/components/ls/transcript";
import { TablePagination } from "@/components/table-pagination";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { usePoll } from "@/hooks/use-poll";
import { t } from "@/i18n";
import { api } from "@/lib/api";
import { fmtTime, ms, num } from "@/lib/format";
import type { LLMCallDetail } from "@/lib/types";
import { useActiveCompanyID } from "@/stores/company/company-store";

function LLMCallSheet({ id, onOpenChange }: { id: number | null; onOpenChange: (o: boolean) => void }) {
  const { data } = usePoll<LLMCallDetail | null>(() => (id === null ? Promise.resolve(null) : api.llmCall(id)), [id]);
  return (
    <Sheet open={id !== null} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 data-[side=right]:sm:max-w-2xl">
        {!data ? (
          <Loading className="h-full" />
        ) : (
          <>
            <SheetHeader className="border-b p-4">
              <SheetTitle className="flex items-center gap-2">
                {t("Model call #{id}", { id: data.id })}
                <Badge variant="outline">{data.model}</Badge>
              </SheetTitle>
              <SheetDescription>
                {data.campaign_name} · {data.role}
                {data.intent_id ? ` · intent #${data.intent_id}` : ""} · {fmtTime(data.ts)}
              </SheetDescription>
            </SheetHeader>
            <div className="flex-1 space-y-4 overflow-y-auto p-4">
              <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
                {[
                  [t("Input"), num(data.input_tokens)],
                  [t("Output"), num(data.output_tokens)],
                  [t("Cache read"), num(data.cache_read)],
                  [t("Cache write"), num(data.cache_write)],
                  [t("Stop reason"), data.stop_reason ?? "—"],
                  [t("Latency"), ms(data.duration_ms)],
                ].map(([k, v]) => (
                  <div key={k} className="rounded-lg border px-3 py-2">
                    <div className="text-muted-foreground text-xs">{k}</div>
                    <div className="font-medium tabular-nums">{v}</div>
                  </div>
                ))}
              </div>
              {data.run && (
                <Button size="sm" variant="outline" asChild>
                  <Link
                    prefetch={false}
                    href={`/function/tasks/detail?id=${data.campaign_id}&tab=sessions&run=${data.run.id}`}
                  >
                    <MessagesSquare />
                    {t("Open session #{id}", { id: data.run.id })}
                  </Link>
                </Button>
              )}
              <div className="space-y-1.5">
                <div className="font-medium text-sm">{t("Response")}</div>
                {data.message ? (
                  <Transcript messages={[data.message]} />
                ) : (
                  <p className="text-muted-foreground text-sm">{t("No response content was recorded for this call.")}</p>
                )}
              </div>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

export default function LLMRecordsPage() {
  const company = useActiveCompanyID();
  const [role, setRole] = useState("all");
  const [model, setModel] = useState("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [open, setOpen] = useState<number | null>(null);
  const { data, loading } = usePoll(
    () =>
      api.llmCalls({
        company: company ?? undefined,
        role: role === "all" ? undefined : role,
        model: model === "all" ? undefined : model,
        offset: (page - 1) * pageSize,
        limit: pageSize,
      }),
    [company, role, model, page, pageSize],
    8000,
  );
  const tot = data?.totals;

  return (
    <div className="flex flex-1 flex-col gap-4 md:gap-6">
      <PageHeader title={t("LLM Recording")} description={t("Every model request the agents made, with token usage, stop reason and latency")} />
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard label={t("Model calls")} value={num(data?.total)} icon={Coins} />
        <StatCard label={t("Input tokens")} value={num(tot?.i)} icon={ArrowDownToLine} />
        <StatCard label={t("Output tokens")} value={num(tot?.o)} icon={ArrowUpFromLine} />
        <StatCard
          label={t("Cache read")}
          value={num(tot?.cr)}
          icon={DatabaseZap}
          tone="text-emerald-600 dark:text-emerald-400"
          hint={tot && tot.i + tot.cr > 0 ? t("{p}% of input served from cache", { p: Math.round((tot.cr / (tot.i + tot.cr)) * 100) }) : undefined}
        />
      </div>

      {!!data?.by_model.length && (
        <Card className="gap-0 pb-0">
          <CardHeader className="pb-4">
            <CardTitle>{t("By model")}</CardTitle>
            <CardDescription>{t("Within the current filter")}</CardDescription>
          </CardHeader>
          <CardContent className="px-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-6">{t("Model")}</TableHead>
                  <TableHead className="text-right">{t("Calls")}</TableHead>
                  <TableHead className="text-right">{t("Input")}</TableHead>
                  <TableHead className="text-right">{t("Cache read")}</TableHead>
                  <TableHead className="pr-6 text-right">{t("Output")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.by_model.map((m) => (
                  <TableRow key={m.model}>
                    <TableCell className="pl-6 font-mono text-xs">{m.model}</TableCell>
                    <TableCell className="text-right tabular-nums">{num(m.calls)}</TableCell>
                    <TableCell className="text-right tabular-nums">{num(m.i)}</TableCell>
                    <TableCell className="text-right tabular-nums">{num(m.cr)}</TableCell>
                    <TableCell className="pr-6 text-right tabular-nums">{num(m.o)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <Card className="gap-0 py-0">
        <CardContent className="px-0">
          <div className="flex flex-wrap items-center gap-3 px-4 py-4 lg:px-6">
            <Select
              value={role}
              onValueChange={(v) => {
                setRole(v);
                setPage(1);
              }}
            >
              <SelectTrigger size="sm" className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("All agents")}</SelectItem>
                <SelectItem value="decomposer">{t("Decomposer")}</SelectItem>
                <SelectItem value="planner">{t("Planner")}</SelectItem>
                <SelectItem value="worker">{t("Worker")}</SelectItem>
              </SelectContent>
            </Select>
            <Select
              value={model}
              onValueChange={(v) => {
                setModel(v);
                setPage(1);
              }}
            >
              <SelectTrigger size="sm" className="w-52">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("All models")}</SelectItem>
                {(data?.models ?? []).map((m) => (
                  <SelectItem key={m} value={m}>
                    {m}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {loading && !data ? (
            <Loading />
          ) : !data?.items.length ? (
            <EmptyRow text={t("No model calls recorded yet.")} />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-4 lg:pl-6">#</TableHead>
                  <TableHead>{t("Agent")}</TableHead>
                  <TableHead>{t("Task")}</TableHead>
                  <TableHead>{t("Model")}</TableHead>
                  <TableHead className="text-right">{t("Input")}</TableHead>
                  <TableHead className="text-right">{t("Cache read")}</TableHead>
                  <TableHead className="text-right">{t("Output")}</TableHead>
                  <TableHead>{t("Stop")}</TableHead>
                  <TableHead className="text-right">{t("Latency")}</TableHead>
                  <TableHead className="pr-4 lg:pr-6">{t("Time")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((r) => (
                  <TableRow key={r.id} className="cursor-pointer" onClick={() => setOpen(r.id)}>
                    <TableCell className="pl-4 font-mono text-muted-foreground text-xs lg:pl-6">{r.id}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-[10px]">
                        {r.role}
                        {r.intent_id ? ` #${r.intent_id}` : ""}
                      </Badge>
                    </TableCell>
                    <TableCell className="max-w-40 truncate text-muted-foreground">{r.campaign_name}</TableCell>
                    <TableCell className="font-mono text-xs">{r.model}</TableCell>
                    <TableCell className="text-right tabular-nums">{num(r.input_tokens)}</TableCell>
                    <TableCell className="text-right text-muted-foreground tabular-nums">{num(r.cache_read)}</TableCell>
                    <TableCell className="text-right tabular-nums">{num(r.output_tokens)}</TableCell>
                    <TableCell className="text-muted-foreground text-xs">{r.stop_reason ?? "—"}</TableCell>
                    <TableCell className="text-right text-xs tabular-nums">{ms(r.duration_ms)}</TableCell>
                    <TableCell className="pr-4 text-muted-foreground text-xs tabular-nums lg:pr-6">{fmtTime(r.ts)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
          <TablePagination
            page={page}
            pageSize={pageSize}
            total={data?.total ?? 0}
            onPageChange={setPage}
            onPageSizeChange={(s) => {
              setPageSize(s);
              setPage(1);
            }}
            pageSizeOptions={[20, 50, 100]}
          />
        </CardContent>
      </Card>
      <LLMCallSheet id={open} onOpenChange={(o) => !o && setOpen(null)} />
    </div>
  );
}
