"use client";

import { Suspense, useEffect, useState } from "react";

import { useSearchParams } from "next/navigation";

import { Download, Flame, Handshake, MessageCircleReply, SearchIcon, Send, ThermometerSun, UserCheck } from "lucide-react";
import { toast } from "sonner";

import { LEAD_STATUSES, LeadSheet } from "@/components/ls/lead-sheet";
import { LeadsTable } from "@/components/ls/leads-table";
import { EmptyRow, Loading } from "@/components/ls/loading";
import { PageHeader } from "@/components/ls/page-header";
import { StatCard } from "@/components/ls/stat-card";
import { TablePagination } from "@/components/table-pagination";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { usePoll } from "@/hooks/use-poll";
import { t } from "@/i18n";
import { api } from "@/lib/api";
import { platformLabel, statusMeta } from "@/lib/status";
import { useActiveCompanyID } from "@/stores/company/company-store";

const SORTS = [
  ["level", "Hottest first"],
  ["fit", "Best fit"],
  ["newest", "Newest found"],
  ["posted", "Newest post"],
] as const;

function LeadsPage() {
  const company = useActiveCompanyID();
  const params = useSearchParams();
  const [level, setLevel] = useState(params.get("level") ?? "all");
  const [status, setStatus] = useState(params.get("status") ?? "all");
  const [platform, setPlatform] = useState("all");
  const [sort, setSort] = useState("level");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [open, setOpen] = useState<number | null>(params.get("id") ? Number(params.get("id")) : null);

  useEffect(() => {
    const h = setTimeout(() => {
      setQuery(q.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(h);
  }, [q]);

  const filters = {
    company: company ?? undefined,
    level: level === "all" ? undefined : level,
    status: status === "all" ? undefined : status,
    platform: platform === "all" ? undefined : platform,
    q: query || undefined,
  };
  const { data: stats, reload: reloadStats } = usePoll(() => api.leadStats({ company: company ?? undefined }), [company], 15000);
  const { data, loading, reload, setData } = usePoll(
    () => api.leads({ ...filters, sort, offset: (page - 1) * pageSize, limit: pageSize }),
    [company, level, status, platform, query, sort, page, pageSize],
    15000,
  );
  const reset = () => setPage(1);

  return (
    <div className="flex flex-1 flex-col gap-4 md:gap-6">
      <PageHeader
        title={t("Leads")}
        description={t("Verified people who described a problem your product solves — each one backed by the post it came from")}
        actions={
          <Button
            variant="outline"
            size="sm"
            onClick={() => api.downloadLeads({ ...filters, sort }).catch((e) => toast.error((e as Error).message))}
          >
            <Download />
            {t("Export CSV")}
          </Button>
        }
      />

      <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
        <StatCard label={t("All leads")} value={stats?.total ?? "—"} icon={UserCheck} />
        <StatCard label={t("Hot")} value={stats?.hot ?? "—"} icon={Flame} tone="text-rose-600 dark:text-rose-400" />
        <StatCard label={t("Warm")} value={stats?.warm ?? "—"} icon={ThermometerSun} tone="text-amber-600 dark:text-amber-400" />
        <StatCard label={t("Contacted")} value={stats?.contacted ?? "—"} icon={Send} tone="text-violet-600 dark:text-violet-400" />
        <StatCard label={t("Replied")} value={stats?.replied ?? "—"} icon={MessageCircleReply} tone="text-amber-600 dark:text-amber-400" />
        <StatCard label={t("Won")} value={stats?.won ?? "—"} icon={Handshake} tone="text-emerald-600 dark:text-emerald-400" />
      </div>

      <Card className="gap-0 py-0">
        <CardContent className="px-0">
          <div className="flex flex-wrap items-center gap-3 px-4 py-4 lg:px-6">
            <InputGroup className="w-full sm:w-72">
              <InputGroupAddon>
                <SearchIcon />
              </InputGroupAddon>
              <InputGroupInput placeholder={t("Search quote, author, pain…")} value={q} onChange={(e) => setQ(e.target.value)} />
            </InputGroup>
            <ToggleGroup
              type="single"
              variant="outline"
              size="sm"
              value={level}
              onValueChange={(v) => {
                if (!v) return;
                setLevel(v);
                reset();
              }}
            >
              {["all", "hot", "warm", "cold"].map((l) => (
                <ToggleGroupItem key={l} value={l} className="px-3">
                  {l === "all" ? t("All") : statusMeta("level", l).label}
                </ToggleGroupItem>
              ))}
            </ToggleGroup>
            <Select
              value={status}
              onValueChange={(v) => {
                setStatus(v);
                reset();
              }}
            >
              <SelectTrigger size="sm" className="w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("Any status")}</SelectItem>
                {LEAD_STATUSES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {statusMeta("lead", s).label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select
              value={platform}
              onValueChange={(v) => {
                setPlatform(v);
                reset();
              }}
            >
              <SelectTrigger size="sm" className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("All platforms")}</SelectItem>
                {Object.keys(stats?.platforms ?? {}).map((p) => (
                  <SelectItem key={p} value={p}>
                    {platformLabel(p)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={sort} onValueChange={setSort}>
              <SelectTrigger size="sm" className="ml-auto w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SORTS.map(([k, l]) => (
                  <SelectItem key={k} value={k}>
                    {t(l)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {loading && !data ? (
            <Loading />
          ) : !data?.items.length ? (
            <EmptyRow text={t("No leads match these filters.")} />
          ) : (
            <LeadsTable
              items={data.items}
              onOpen={setOpen}
              onStatus={(id, s) => {
                setData((d) => (d ? { ...d, items: d.items.map((l) => (l.node_id === id ? { ...l, status: s } : l)) } : d));
                reloadStats();
              }}
            />
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
            pageSizeOptions={[25, 50, 100]}
          />
        </CardContent>
      </Card>
      <LeadSheet
        leadId={open}
        onOpenChange={(o) => !o && setOpen(null)}
        onChanged={() => {
          reload();
          reloadStats();
        }}
      />
    </div>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <LeadsPage />
    </Suspense>
  );
}
