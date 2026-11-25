"use client";

import * as React from "react";

import { EmptyRow, Loading } from "@/components/ls/loading";
import { NodeSheet } from "@/components/ls/node-sheet";
import { StatusBadge } from "@/components/status-badge";
import { Card, CardContent } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { usePoll } from "@/hooks/use-poll";
import { t } from "@/i18n";
import { api } from "@/lib/api";
import { ago, num } from "@/lib/format";
import { platformLabel } from "@/lib/status";
import type { TaskDetail } from "@/lib/types";

const STATES = ["all", "running", "open", "done", "exhausted", "blocked"] as const;

export function IntentsTab({ task, onOpenSession }: { task: TaskDetail; onOpenSession: (runId: number) => void }) {
  const { data } = usePoll(() => api.intents(task.id), [task.id], task.status === "running" ? 4000 : 0);
  const [state, setState] = React.useState<string>("all");
  const [node, setNode] = React.useState<number | null>(null);

  if (!data) return <Loading className="min-h-96" />;
  const rows = state === "all" ? data : data.filter((i) => i.state === state);

  return (
    <Card className="gap-0 py-0">
      <CardContent className="px-0">
        <div className="flex flex-wrap items-center gap-3 px-4 py-4 lg:px-6">
          <ToggleGroup type="single" variant="outline" size="sm" value={state} onValueChange={(v) => v && setState(v)}>
            {STATES.map((s) => (
              <ToggleGroupItem key={s} value={s} className="px-3 capitalize">
                {s === "all" ? t("All") : t(s)}
                <span className="ml-1 text-muted-foreground text-xs tabular-nums">
                  {s === "all" ? data.length : data.filter((i) => i.state === s).length}
                </span>
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
        </div>
        {!rows.length ? (
          <EmptyRow text={t("No intents yet — the planner creates them each round.")} />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-16 pl-4 lg:pl-6">#</TableHead>
                <TableHead className="min-w-80">{t("Intent")}</TableHead>
                <TableHead>{t("Platform")}</TableHead>
                <TableHead>{t("State")}</TableHead>
                <TableHead>{t("Worker")}</TableHead>
                <TableHead className="text-right">{t("Leads")}</TableHead>
                <TableHead className="text-right">{t("Facts")}</TableHead>
                <TableHead className="text-right">{t("Tokens")}</TableHead>
                <TableHead className="pr-4 lg:pr-6">{t("Updated")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((i) => (
                <TableRow key={i.id} className="cursor-pointer" onClick={() => setNode(i.id)}>
                  <TableCell className="pl-4 font-mono text-muted-foreground text-xs lg:pl-6">{i.id}</TableCell>
                  <TableCell className="max-w-[32rem] whitespace-normal">
                    <span className="line-clamp-2">{i.summary}</span>
                    {i.goal_id && <span className="text-muted-foreground text-xs">{t("for goal #{id}", { id: i.goal_id })}</span>}
                  </TableCell>
                  <TableCell>{platformLabel(i.platform)}</TableCell>
                  <TableCell>
                    <StatusBadge domain="intent" value={i.state} dot />
                  </TableCell>
                  <TableCell className="text-muted-foreground text-xs">{i.owner ?? "—"}</TableCell>
                  <TableCell className="text-right tabular-nums">{i.leads}</TableCell>
                  <TableCell className="text-right tabular-nums">{i.facts}</TableCell>
                  <TableCell className="text-right text-muted-foreground tabular-nums">{num(i.tokens)}</TableCell>
                  <TableCell className="pr-4 text-muted-foreground text-xs lg:pr-6">{ago(i.updated_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
        <NodeSheet
          nodeId={node}
          onOpenChange={(o) => !o && setNode(null)}
          onSelect={setNode}
          onOpenSession={(id) => {
            setNode(null);
            onOpenSession(id);
          }}
        />
      </CardContent>
    </Card>
  );
}
