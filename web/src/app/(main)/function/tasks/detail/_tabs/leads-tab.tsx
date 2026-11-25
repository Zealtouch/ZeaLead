"use client";

import * as React from "react";

import { Download, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { LeadSheet } from "@/components/ls/lead-sheet";
import { LeadsTable } from "@/components/ls/leads-table";
import { EmptyRow, Loading } from "@/components/ls/loading";
import { TablePagination } from "@/components/table-pagination";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { usePoll } from "@/hooks/use-poll";
import { t } from "@/i18n";
import { api } from "@/lib/api";
import type { TaskDetail } from "@/lib/types";

export function LeadsTab({ task }: { task: TaskDetail }) {
  const [level, setLevel] = React.useState("all");
  const [page, setPage] = React.useState(1);
  const [pageSize, setPageSize] = React.useState(25);
  const [open, setOpen] = React.useState<number | null>(null);
  const lv = level === "all" ? undefined : level;
  const { data, loading, reload, setData } = usePoll(
    () => api.leads({ campaign: task.id, level: lv, sort: "level", offset: (page - 1) * pageSize, limit: pageSize }),
    [task.id, lv, page, pageSize],
    task.status === "running" ? 8000 : 0,
  );

  return (
    <Card className="gap-0 py-0">
      <CardContent className="px-0">
        <div className="flex flex-wrap items-center gap-3 px-4 py-4 lg:px-6">
          <ToggleGroup
            type="single"
            variant="outline"
            size="sm"
            value={level}
            onValueChange={(v) => {
              if (!v) return;
              setLevel(v);
              setPage(1);
            }}
          >
            <ToggleGroupItem value="all" className="px-3">
              {t("All")} <span className="ml-1 text-muted-foreground text-xs">{task.leads.hot + task.leads.warm + task.leads.cold}</span>
            </ToggleGroupItem>
            <ToggleGroupItem value="hot" className="px-3">
              {t("Hot")} <span className="ml-1 text-muted-foreground text-xs">{task.leads.hot}</span>
            </ToggleGroupItem>
            <ToggleGroupItem value="warm" className="px-3">
              {t("Warm")} <span className="ml-1 text-muted-foreground text-xs">{task.leads.warm}</span>
            </ToggleGroupItem>
            <ToggleGroupItem value="cold" className="px-3">
              {t("Cold")} <span className="ml-1 text-muted-foreground text-xs">{task.leads.cold}</span>
            </ToggleGroupItem>
          </ToggleGroup>
          <Button
            size="sm"
            variant="outline"
            className="ml-auto"
            title={t("Write a personal reply and DM for every lead that has none yet")}
            onClick={() =>
              api
                .draftTaskMessages(task.id)
                .then((r) =>
                  r.queued
                    ? toast.success(t("Drafting messages for {n} leads — they appear as each one finishes", { n: r.queued }))
                    : toast.info(t("Every lead already has messages")),
                )
                .catch((e) => toast.error((e as Error).message))
            }
          >
            <Sparkles />
            {t("Draft missing messages")}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={() => api.downloadLeads({ campaign: task.id, level: lv }).catch((e) => toast.error((e as Error).message))}
          >
            <Download />
            {t("Export CSV")}
          </Button>
        </div>
        {loading && !data ? (
          <Loading />
        ) : !data?.items.length ? (
          <EmptyRow text={t("No leads yet. Workers save a lead only after reading the post and verifying it.")} />
        ) : (
          <LeadsTable
            items={data.items}
            showTask={false}
            onOpen={setOpen}
            onStatus={(id, s) =>
              setData((d) => (d ? { ...d, items: d.items.map((l) => (l.node_id === id ? { ...l, status: s } : l)) } : d))
            }
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
        <LeadSheet leadId={open} onOpenChange={(o) => !o && setOpen(null)} onChanged={reload} />
      </CardContent>
    </Card>
  );
}
