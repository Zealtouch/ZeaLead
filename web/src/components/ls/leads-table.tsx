"use client";

import Link from "next/link";

import { Eye, MessageCircle } from "lucide-react";

import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { t } from "@/i18n";
import { ago } from "@/lib/format";
import { platformLabel } from "@/lib/status";
import type { Lead, LeadStatus } from "@/lib/types";
import { cn } from "@/lib/utils";

import { ExtLink } from "./ext-link";
import { LeadStatusSelect } from "./lead-sheet";

function fitTone(score: number) {
  return score >= 80 ? "text-emerald-600 dark:text-emerald-400" : score >= 60 ? "text-amber-600 dark:text-amber-400" : "text-muted-foreground";
}

export function LeadsTable({
  items,
  showTask = true,
  onOpen,
  onStatus,
}: {
  items: Lead[];
  showTask?: boolean;
  onOpen: (id: number) => void;
  onStatus: (id: number, s: LeadStatus) => void;
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead className="w-20 pl-4">{t("Intent")}</TableHead>
          <TableHead className="min-w-44">{t("Person")}</TableHead>
          <TableHead className="min-w-80">{t("Need and evidence")}</TableHead>
          <TableHead className="w-14 text-right">{t("Fit")}</TableHead>
          <TableHead className="w-36">{t("Status")}</TableHead>
          {showTask && <TableHead className="min-w-36">{t("Task")}</TableHead>}
          <TableHead className="w-20">{t("Found")}</TableHead>
          <TableHead className="w-12 pr-4 text-right">{t("Actions")}</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {items.map((l) => (
          <TableRow key={l.node_id} className={cn(l.status === "dismissed" && "opacity-60")}>
            <TableCell className="pl-4">
              <StatusBadge domain="level" value={l.intent_level} dot />
            </TableCell>
            <TableCell>
              <div className="flex min-w-0 flex-col gap-0.5">
                <ExtLink href={l.author_url} className="max-w-48 font-medium text-foreground" icon={false}>
                  {l.author || t("unknown")}
                </ExtLink>
                <Badge variant="outline" className="w-fit text-[10px]">
                  {platformLabel(l.platform)}
                </Badge>
              </div>
            </TableCell>
            <TableCell className="whitespace-normal">
              <button type="button" className="block w-full text-left" onClick={() => onOpen(l.node_id)}>
                <div className="flex items-center gap-1.5">
                  <span className="line-clamp-1 font-medium">{l.pain || t("(no summary)")}</span>
                  {l.drafted_at && (l.dm_message || l.suggested_reply) ? (
                    <MessageCircle className="size-3.5 shrink-0 text-violet-500" aria-label={t("Messages ready")} />
                  ) : null}
                </div>
                <div className="line-clamp-2 text-muted-foreground text-xs">“{l.quote}”</div>
              </button>
            </TableCell>
            <TableCell className={cn("text-right font-medium tabular-nums", fitTone(l.fit_score))}>{l.fit_score}</TableCell>
            <TableCell>
              <LeadStatusSelect id={l.node_id} value={l.status} onChange={(s) => onStatus(l.node_id, s)} />
            </TableCell>
            {showTask && (
              <TableCell>
                <Link
                  prefetch={false}
                  href={`/function/tasks/detail?id=${l.campaign_id}`}
                  className="line-clamp-1 max-w-44 text-muted-foreground hover:text-foreground hover:underline"
                >
                  {l.campaign_name ?? `#${l.campaign_id}`}
                </Link>
              </TableCell>
            )}
            <TableCell className="text-muted-foreground text-xs tabular-nums">{ago(l.created_at)}</TableCell>
            <TableCell className="pr-4 text-right">
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button variant="ghost" size="icon-sm" onClick={() => onOpen(l.node_id)} aria-label={t("View lead")}>
                    <Eye />
                  </Button>
                </TooltipTrigger>
                <TooltipContent>{t("View lead")}</TooltipContent>
              </Tooltip>
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
