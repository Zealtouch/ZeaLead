"use client";

import { useState } from "react";

import Link from "next/link";

import { AlertTriangle, CheckCircle2 } from "lucide-react";

import { TablePagination } from "@/components/table-pagination";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { usePoll } from "@/hooks/use-poll";
import { t } from "@/i18n";
import { api } from "@/lib/api";
import { fmtTime, ms, pretty } from "@/lib/format";
import type { ToolCallDetail } from "@/lib/types";
import { useActiveCompany } from "@/stores/company/company-store";

import { EmptyRow, Loading } from "./loading";

function Pre({ text }: { text: string }) {
  return (
    <pre className="max-h-[50vh] overflow-auto whitespace-pre-wrap break-words rounded-lg bg-muted/50 p-3 font-mono text-[11px] leading-relaxed">
      {text}
    </pre>
  );
}

export function ToolCallSheet({ id, onOpenChange }: { id: number | null; onOpenChange: (o: boolean) => void }) {
  const { data } = usePoll<ToolCallDetail | null>(() => (id === null ? Promise.resolve(null) : api.toolCall(id)), [id]);
  return (
    <Sheet open={id !== null} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 data-[side=right]:sm:max-w-2xl">
        {!data ? (
          <Loading className="h-full" />
        ) : (
          <>
            <SheetHeader className="border-b p-4">
              <SheetTitle className="flex items-center gap-2 font-mono text-base">
                {data.is_error ? (
                  <AlertTriangle className="size-4 text-red-500" />
                ) : (
                  <CheckCircle2 className="size-4 text-emerald-500" />
                )}
                {data.tool}
              </SheetTitle>
              <SheetDescription>
                {data.campaign_name} · {data.role}
                {data.intent_id ? ` · intent #${data.intent_id}` : ""} · {fmtTime(data.ts)} · {ms(data.duration_ms)}
              </SheetDescription>
            </SheetHeader>
            <div className="flex-1 space-y-4 overflow-y-auto p-4">
              <div className="space-y-1.5">
                <div className="font-medium text-sm">{t("Input")}</div>
                <Pre text={pretty(data.input)} />
              </div>
              <div className="space-y-1.5">
                <div className="font-medium text-sm">{t("Output")}</div>
                <p className="text-muted-foreground text-xs">
                  {t("Text from collected posts is shown as data inside its untrusted-content frame, exactly as the agent saw it.")}
                </p>
                <Pre text={data.output || ""} />
              </div>
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

export function ToolCallsView({ campaign }: { campaign?: number }) {
  const company = useActiveCompany();
  const [tool, setTool] = useState("all");
  const [errors, setErrors] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [open, setOpen] = useState<number | null>(null);
  const { data, loading } = usePoll(
    () =>
      api.toolCalls({
        company: campaign ? undefined : company,
        campaign,
        tool: tool === "all" ? undefined : tool,
        errors,
        offset: (page - 1) * pageSize,
        limit: pageSize,
      }),
    [company, campaign, tool, errors, page, pageSize],
    5000,
  );

  return (
    <Card className="gap-0 py-0">
      <CardContent className="px-0">
        <div className="flex flex-wrap items-center gap-3 px-4 py-4 lg:px-6">
          <Select
            value={tool}
            onValueChange={(v) => {
              setTool(v);
              setPage(1);
            }}
          >
            <SelectTrigger size="sm" className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("All tools")}</SelectItem>
              {(data?.tools ?? []).map((x) => (
                <SelectItem key={x} value={x}>
                  {x}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <label className="flex items-center gap-2 text-sm">
            <Switch
              checked={errors}
              onCheckedChange={(v) => {
                setErrors(v);
                setPage(1);
              }}
            />
            {t("Errors only")}
          </label>
          <span className="text-muted-foreground text-xs">{t("{n} calls", { n: data?.total ?? 0 })}</span>
        </div>
        {loading && !data ? (
          <Loading />
        ) : !data?.items.length ? (
          <EmptyRow text={t("No tool calls recorded yet.")} />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-12 pl-4 lg:pl-6" />
                <TableHead>{t("Tool")}</TableHead>
                <TableHead className="min-w-72">{t("Input")}</TableHead>
                <TableHead>{t("Agent")}</TableHead>
                {!campaign && <TableHead>{t("Task")}</TableHead>}
                <TableHead className="text-right">{t("Duration")}</TableHead>
                <TableHead className="text-right">{t("Output")}</TableHead>
                <TableHead className="pr-4 lg:pr-6">{t("Time")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.items.map((r) => (
                <TableRow key={r.id} className="cursor-pointer" onClick={() => setOpen(r.id)}>
                  <TableCell className="pl-4 lg:pl-6">
                    {r.is_error ? (
                      <AlertTriangle className="size-4 text-red-500" aria-label={t("error")} />
                    ) : (
                      <CheckCircle2 className="size-4 text-emerald-500" aria-label={t("ok")} />
                    )}
                  </TableCell>
                  <TableCell className="font-medium font-mono text-xs">{r.tool}</TableCell>
                  <TableCell className="max-w-96 truncate font-mono text-muted-foreground text-xs">{r.input}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className="text-[10px]">
                      {r.role}
                      {r.intent_id ? ` #${r.intent_id}` : ""}
                    </Badge>
                  </TableCell>
                  {!campaign && (
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <Link
                        prefetch={false}
                        href={`/function/tasks/detail?id=${r.campaign_id}&tab=tools`}
                        className="line-clamp-1 max-w-40 text-muted-foreground hover:underline"
                      >
                        {r.campaign_name}
                      </Link>
                    </TableCell>
                  )}
                  <TableCell className="text-right text-xs tabular-nums">{ms(r.duration_ms)}</TableCell>
                  <TableCell className="text-right text-muted-foreground text-xs tabular-nums">
                    {r.output_len ? `${(r.output_len / 1024).toFixed(1)} KB` : "—"}
                  </TableCell>
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
        <ToolCallSheet id={open} onOpenChange={(o) => !o && setOpen(null)} />
      </CardContent>
    </Card>
  );
}
