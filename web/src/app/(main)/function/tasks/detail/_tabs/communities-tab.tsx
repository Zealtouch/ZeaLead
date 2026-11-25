"use client";

import { ExtLink } from "@/components/ls/ext-link";
import { EmptyRow, Loading } from "@/components/ls/loading";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { usePoll } from "@/hooks/use-poll";
import { t } from "@/i18n";
import { api } from "@/lib/api";
import { platformLabel } from "@/lib/status";
import type { TaskDetail } from "@/lib/types";

// Communities this task has touched: subreddits, hashtags, search queries, groups. Mined
// means a worker fully read it; the planner avoids re-mining those.
export function CommunitiesTab({ task }: { task: TaskDetail }) {
  const { data } = usePoll(() => api.taskCommunities(task.id), [task.id], task.status === "running" ? 8000 : 0);
  if (!data) return <Loading className="min-h-96" />;
  const rows = [...data].sort((a, b) => b.leads - a.leads || b.targeted - a.targeted);

  return (
    <Card className="gap-0 pb-0">
      <CardHeader className="pb-4">
        <CardTitle>{t("Communities")}</CardTitle>
        <CardDescription>{t("Where this task looked, and what each place produced")}</CardDescription>
      </CardHeader>
      <CardContent className="px-0">
        {!rows.length ? (
          <EmptyRow text={t("No communities yet.")} />
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="pl-6">{t("Community")}</TableHead>
                <TableHead>{t("Platform")}</TableHead>
                <TableHead className="text-right">{t("Intents")}</TableHead>
                <TableHead>{t("Mined")}</TableHead>
                <TableHead className="text-right">{t("Facts")}</TableHead>
                <TableHead className="pr-6 text-right">{t("Leads")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((c) => (
                <TableRow key={c.id}>
                  <TableCell className="pl-6 font-medium">
                    <ExtLink href={c.url} icon={false}>
                      {c.key}
                    </ExtLink>
                  </TableCell>
                  <TableCell>{platformLabel(c.platform)}</TableCell>
                  <TableCell className="text-right tabular-nums">{c.targeted}</TableCell>
                  <TableCell>
                    {c.mined ? (
                      <Badge variant="secondary">{t("Mined")}</Badge>
                    ) : (
                      <span className="text-muted-foreground text-xs">{t("seen")}</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{c.facts}</TableCell>
                  <TableCell className="pr-6 text-right font-medium tabular-nums">{c.leads}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
