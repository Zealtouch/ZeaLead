"use client";

import * as React from "react";

import Link from "next/link";

import { MessageSquareQuote, ShieldAlert, ShieldCheck, UserRound } from "lucide-react";
import { toast } from "sonner";

import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { t } from "@/i18n";
import { api } from "@/lib/api";
import { fmtDate, fmtTime } from "@/lib/format";
import { platformLabel, statusMeta } from "@/lib/status";
import type { LeadDetail, LeadStatus } from "@/lib/types";

import { ExtLink } from "./ext-link";
import { LeadMessages } from "./lead-messages";
import { Loading } from "./loading";

export const LEAD_STATUSES: LeadStatus[] = ["new", "contacted", "replied", "won", "dismissed"];

export function LeadStatusSelect({
  id,
  value,
  onChange,
  className = "h-7 w-32",
}: {
  id: number;
  value: LeadStatus;
  onChange?: (s: LeadStatus) => void;
  className?: string;
}) {
  return (
    <Select
      value={value}
      onValueChange={(v) => {
        api
          .setLeadStatus(id, v as LeadStatus)
          .then(() => onChange?.(v as LeadStatus))
          .catch((e) => toast.error((e as Error).message));
      }}
    >
      <SelectTrigger size="sm" className={className} aria-label={t("Outreach status")}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {LEAD_STATUSES.map((s) => (
          <SelectItem key={s} value={s}>
            {statusMeta("lead", s).label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

function Section({ icon: Icon, title, children }: { icon: React.ElementType; title: string; children: React.ReactNode }) {
  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 font-medium text-sm">
        <Icon className="size-4 text-muted-foreground" />
        {title}
      </div>
      <div className="text-sm">{children}</div>
    </div>
  );
}

// LeadSheet: everything known about one lead. All text here was written by strangers or
// derived from it, so it is rendered as plain text; links are http(s) only.
export function LeadSheet({
  leadId,
  onOpenChange,
  onChanged,
}: {
  leadId: number | null;
  onOpenChange: (open: boolean) => void;
  onChanged?: () => void;
}) {
  const [lead, setLead] = React.useState<LeadDetail | null>(null);

  React.useEffect(() => {
    setLead(null);
    if (leadId === null) return;
    api
      .lead(leadId)
      .then(setLead)
      .catch((e) => toast.error((e as Error).message));
  }, [leadId]);

  const counter = typeof lead?.payload?.counterevidence === "string" ? (lead.payload.counterevidence as string) : "";

  return (
    <Sheet open={leadId !== null} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 data-[side=right]:sm:max-w-xl">
        {!lead ? (
          <Loading className="h-full" />
        ) : (
          <>
            <SheetHeader className="border-b p-4">
              <div className="flex flex-wrap items-center gap-2 pr-8">
                <StatusBadge domain="level" value={lead.intent_level} dot />
                <Badge variant="outline">{platformLabel(lead.platform)}</Badge>
                <Badge variant="outline" className="tabular-nums">
                  {t("Fit {score}", { score: lead.fit_score })}
                </Badge>
                <span className="ml-auto font-mono text-muted-foreground text-xs">#{lead.node_id}</span>
              </div>
              <SheetTitle className="pt-1 text-base leading-snug">{lead.pain || t("Lead")}</SheetTitle>
              <SheetDescription className="flex flex-wrap items-center gap-x-3 gap-y-1">
                <span>{t("Posted {date}", { date: fmtDate(lead.posted_at) })}</span>
                <span>{t("Found {date}", { date: fmtTime(lead.created_at) })}</span>
                {lead.campaign_name && (
                  <Link
                    prefetch={false}
                    href={`/function/tasks/detail?id=${lead.campaign_id}&tab=leads`}
                    className="text-primary hover:underline"
                  >
                    {lead.campaign_name}
                  </Link>
                )}
              </SheetDescription>
            </SheetHeader>
            <div className="flex-1 space-y-5 overflow-y-auto p-4">
              <div className="flex items-center justify-between gap-3 rounded-lg border bg-muted/30 p-3">
                <div className="flex min-w-0 items-center gap-2">
                  <UserRound className="size-4 shrink-0 text-muted-foreground" />
                  <ExtLink href={lead.author_url} className="font-medium">
                    {lead.author || t("unknown author")}
                  </ExtLink>
                </div>
                <LeadStatusSelect
                  id={lead.node_id}
                  value={lead.status}
                  onChange={(s) => {
                    setLead({ ...lead, status: s });
                    onChanged?.();
                  }}
                />
              </div>

              <Section icon={MessageSquareQuote} title={t("What they said")}>
                <blockquote className="whitespace-pre-wrap break-words border-l-2 border-primary pl-3 text-foreground/90">
                  “{lead.quote}”
                </blockquote>
                <div className="mt-2">
                  <ExtLink href={lead.url}>{t("Open the post")}</ExtLink>
                </div>
              </Section>

              {lead.reason && (
                <Section icon={ShieldCheck} title={t("Why it survived the adversarial check")}>
                  <p className="whitespace-pre-wrap text-muted-foreground">{lead.reason}</p>
                </Section>
              )}
              {counter && (
                <Section icon={ShieldAlert} title={t("What argues against it")}>
                  <p className="whitespace-pre-wrap text-muted-foreground">{counter}</p>
                </Section>
              )}

              <LeadMessages
                lead={lead}
                onChange={(l) => {
                  setLead(l);
                  onChanged?.();
                }}
              />

              {lead.evidence.length > 0 && (
                <>
                  <Separator />
                  <div className="space-y-3">
                    <div className="font-medium text-sm">
                      {t("Evidence ({n})", { n: lead.evidence.length })}
                    </div>
                    {lead.evidence.map((e, i) => (
                      <div key={`${e.url}-${i}`} className="space-y-2 rounded-lg border p-3 text-sm">
                        <div className="flex flex-wrap items-center gap-2 text-muted-foreground text-xs">
                          <Badge variant="outline">{platformLabel(e.platform)}</Badge>
                          <span>{fmtDate(e.posted_at)}</span>
                          <ExtLink href={e.url} className="ml-auto max-w-60">
                            {t("source")}
                          </ExtLink>
                        </div>
                        <p className="whitespace-pre-wrap break-words font-medium">“{e.quote}”</p>
                        <details>
                          <summary className="cursor-pointer text-muted-foreground text-xs">
                            {t("Full captured text")}
                          </summary>
                          <p className="mt-2 max-h-64 overflow-y-auto whitespace-pre-wrap break-words rounded bg-muted/50 p-2 text-xs">
                            {e.text}
                          </p>
                        </details>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
