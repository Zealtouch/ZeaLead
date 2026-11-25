"use client";

import { useEffect, useState } from "react";

import Link from "next/link";

import { SearchIcon } from "lucide-react";

import { EmptyRow, Loading } from "@/components/ls/loading";
import { PageHeader } from "@/components/ls/page-header";
import { TablePagination } from "@/components/table-pagination";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { usePoll } from "@/hooks/use-poll";
import { t } from "@/i18n";
import { api } from "@/lib/api";
import { fmtTime } from "@/lib/format";
import { useActiveCompanyID } from "@/stores/company/company-store";

const ROLES = ["system", "operator", "decomposer", "planner", "worker"];

function LogSheet({ id, onOpenChange }: { id: number | null; onOpenChange: (o: boolean) => void }) {
  const { data } = usePoll(() => (id === null ? Promise.resolve(null) : api.activityDetail(id)), [id]);
  return (
    <Sheet open={id !== null} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 data-[side=right]:sm:max-w-xl">
        {!data ? (
          <Loading className="h-full" />
        ) : (
          <>
            <SheetHeader className="border-b p-4">
              <SheetTitle className="flex items-center gap-2">
                <Badge variant="outline">{data.role}</Badge>
                {data.kind}
              </SheetTitle>
              <SheetDescription>
                {fmtTime(data.ts)}
                {data.intent_id ? ` · intent #${data.intent_id}` : ""}
              </SheetDescription>
            </SheetHeader>
            <div className="flex-1 space-y-3 overflow-y-auto p-4">
              <p className="whitespace-pre-wrap text-sm">{data.summary}</p>
              {data.detail && (
                <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap break-words rounded-lg bg-muted/50 p-3 font-mono text-[11px]">
                  {data.detail}
                </pre>
              )}
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

// Logs: the activity stream of every task — dispatches, findings, errors, operator hints.
export default function LogsPage() {
  const company = useActiveCompanyID();
  const [role, setRole] = useState("all");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);
  const [open, setOpen] = useState<number | null>(null);

  useEffect(() => {
    const h = setTimeout(() => {
      setQuery(q.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(h);
  }, [q]);

  const { data, loading } = usePoll(
    () =>
      api.logs({
        company: company ?? undefined,
        role: role === "all" ? undefined : role,
        q: query || undefined,
        offset: (page - 1) * pageSize,
        limit: pageSize,
      }),
    [company, role, query, page, pageSize],
    5000,
  );

  return (
    <div className="flex flex-1 flex-col gap-4 md:gap-6">
      <PageHeader title={t("Logs")} description={t("The activity stream of every task, newest first")} />
      <Card className="gap-0 py-0">
        <CardContent className="px-0">
          <div className="flex flex-wrap items-center gap-3 px-4 py-4 lg:px-6">
            <InputGroup className="w-full sm:w-72">
              <InputGroupAddon>
                <SearchIcon />
              </InputGroupAddon>
              <InputGroupInput placeholder={t("Search logs…")} value={q} onChange={(e) => setQ(e.target.value)} />
            </InputGroup>
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
                <SelectItem value="all">{t("All sources")}</SelectItem>
                {ROLES.map((r) => (
                  <SelectItem key={r} value={r} className="capitalize">
                    {t(r)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span className="text-muted-foreground text-xs">{t("{n} entries", { n: data?.total ?? 0 })}</span>
          </div>
          {loading && !data ? (
            <Loading />
          ) : !data?.items.length ? (
            <EmptyRow text={t("No log entries.")} />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-4 lg:pl-6">{t("Time")}</TableHead>
                  <TableHead>{t("Source")}</TableHead>
                  <TableHead>{t("Kind")}</TableHead>
                  <TableHead className="min-w-96">{t("Message")}</TableHead>
                  <TableHead className="pr-4 lg:pr-6">{t("Task")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((r) => (
                  <TableRow key={r.id} className="cursor-pointer" onClick={() => setOpen(r.id)}>
                    <TableCell className="pl-4 text-muted-foreground text-xs tabular-nums lg:pl-6">{fmtTime(r.ts)}</TableCell>
                    <TableCell>
                      <Badge variant="outline" className="text-[10px]">
                        {r.role}
                        {r.intent_id ? ` #${r.intent_id}` : ""}
                      </Badge>
                    </TableCell>
                    <TableCell className="font-mono text-xs">{r.kind}</TableCell>
                    <TableCell className="max-w-[40rem] truncate text-sm">{r.summary}</TableCell>
                    <TableCell className="pr-4 lg:pr-6" onClick={(e) => e.stopPropagation()}>
                      <Link
                        prefetch={false}
                        href={`/function/tasks/detail?id=${r.campaign_id}&tab=overview`}
                        className="line-clamp-1 max-w-40 text-muted-foreground hover:underline"
                      >
                        {r.campaign_name}
                      </Link>
                    </TableCell>
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
      <LogSheet id={open} onOpenChange={(o) => !o && setOpen(null)} />
    </div>
  );
}
