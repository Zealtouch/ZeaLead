"use client";

import { useEffect, useState } from "react";

import { SearchIcon } from "lucide-react";

import { ExtLink } from "@/components/ls/ext-link";
import { EmptyRow, Loading } from "@/components/ls/loading";
import { PageHeader } from "@/components/ls/page-header";
import { TablePagination } from "@/components/table-pagination";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { usePoll } from "@/hooks/use-poll";
import { t } from "@/i18n";
import { api } from "@/lib/api";
import { ago } from "@/lib/format";
import { PLATFORM_LABEL, platformLabel } from "@/lib/status";
import { useActiveCompanyID } from "@/stores/company/company-store";

// Communities across every task: the places where your customers talk. Sorted by the
// leads they produced, so the best channels for manual outreach rise to the top.
export default function CommunitiesPage() {
  const company = useActiveCompanyID();
  const [platform, setPlatform] = useState("all");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(50);

  useEffect(() => {
    const h = setTimeout(() => {
      setQuery(q.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(h);
  }, [q]);

  const { data, loading } = usePoll(
    () =>
      api.communities({
        company: company ?? undefined,
        platform: platform === "all" ? undefined : platform,
        q: query || undefined,
        offset: (page - 1) * pageSize,
        limit: pageSize,
      }),
    [company, platform, query, page, pageSize],
    20000,
  );

  return (
    <div className="flex flex-1 flex-col gap-4 md:gap-6">
      <PageHeader
        title={t("Communities")}
        description={t("Subreddits, hashtags, forums and searches where your customers were found, ranked by leads")}
      />
      <Card className="gap-0 py-0">
        <CardContent className="px-0">
          <div className="flex flex-wrap items-center gap-3 px-4 py-4 lg:px-6">
            <InputGroup className="w-full sm:w-72">
              <InputGroupAddon>
                <SearchIcon />
              </InputGroupAddon>
              <InputGroupInput placeholder={t("Search communities…")} value={q} onChange={(e) => setQ(e.target.value)} />
            </InputGroup>
            <Select
              value={platform}
              onValueChange={(v) => {
                setPlatform(v);
                setPage(1);
              }}
            >
              <SelectTrigger size="sm" className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("All platforms")}</SelectItem>
                {Object.keys(PLATFORM_LABEL).map((p) => (
                  <SelectItem key={p} value={p}>
                    {platformLabel(p)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span className="text-muted-foreground text-xs">{t("{n} communities", { n: data?.total ?? 0 })}</span>
          </div>
          {loading && !data ? (
            <Loading />
          ) : !data?.items.length ? (
            <EmptyRow text={t("No communities yet. They appear as workers explore.")} />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-4 lg:pl-6">{t("Community")}</TableHead>
                  <TableHead>{t("Platform")}</TableHead>
                  <TableHead className="text-right">{t("Tasks")}</TableHead>
                  <TableHead className="text-right">{t("Intents")}</TableHead>
                  <TableHead>{t("Mined")}</TableHead>
                  <TableHead className="text-right">{t("Facts")}</TableHead>
                  <TableHead className="text-right">{t("Leads")}</TableHead>
                  <TableHead className="pr-4 lg:pr-6">{t("First seen")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.items.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell className="pl-4 lg:pl-6">
                      <div className="flex flex-col">
                        <ExtLink href={c.url} icon={false} className="font-medium">
                          {c.key}
                        </ExtLink>
                        {c.title && c.title !== c.key && <span className="line-clamp-1 text-muted-foreground text-xs">{c.title}</span>}
                      </div>
                    </TableCell>
                    <TableCell>{platformLabel(c.platform)}</TableCell>
                    <TableCell className="text-right tabular-nums">{c.campaigns}</TableCell>
                    <TableCell className="text-right tabular-nums">{c.intents}</TableCell>
                    <TableCell>
                      {c.mined ? <Badge variant="secondary">{t("Mined")}</Badge> : <span className="text-muted-foreground text-xs">{t("seen")}</span>}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">{c.facts}</TableCell>
                    <TableCell className="text-right font-medium tabular-nums">{c.leads}</TableCell>
                    <TableCell className="pr-4 text-muted-foreground text-xs lg:pr-6">{ago(c.first_seen)}</TableCell>
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
            pageSizeOptions={[25, 50, 100]}
          />
        </CardContent>
      </Card>
    </div>
  );
}
