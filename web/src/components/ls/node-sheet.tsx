"use client";

import * as React from "react";

import { MessagesSquare, UserCheck } from "lucide-react";
import { toast } from "sonner";

import { Markdown } from "@/components/markdown";
import { StatusBadge } from "@/components/status-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { t } from "@/i18n";
import { api } from "@/lib/api";
import { fmtTime, num } from "@/lib/format";
import { platformLabel } from "@/lib/status";
import type { NodeDetail, NodeRef } from "@/lib/types";
import { cn } from "@/lib/utils";

import { typeMeta } from "./exploration-graph";
import { ExtLink } from "./ext-link";
import { Loading } from "./loading";

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-3 py-1.5 text-sm">
      <span className="w-24 shrink-0 text-muted-foreground">{label}</span>
      <span className="min-w-0 flex-1 break-words">{children}</span>
    </div>
  );
}

function Refs({ items, onSelect }: { items: NodeRef[]; onSelect: (id: number) => void }) {
  if (!items.length) return <span className="text-muted-foreground">—</span>;
  return (
    <div className="flex flex-col gap-1">
      {items.map((r) => (
        <button
          key={`${r.kind}-${r.id}`}
          type="button"
          onClick={() => onSelect(r.id)}
          className="flex items-start gap-2 rounded-md px-1.5 py-1 text-left hover:bg-muted"
        >
          <Badge variant="outline" className="shrink-0 text-[10px]">
            {r.kind} #{r.id}
          </Badge>
          <span className="line-clamp-2 text-xs">{r.summary}</span>
        </button>
      ))}
    </div>
  );
}

// NodeSheet: one exploration-graph node — why it exists (parents), what it produced, the
// communities it is anchored to, and for intents the worker's report and session.
export function NodeSheet({
  nodeId,
  onOpenChange,
  onSelect,
  onOpenLead,
  onOpenSession,
}: {
  nodeId: number | null;
  onOpenChange: (o: boolean) => void;
  onSelect: (id: number) => void;
  onOpenLead?: (id: number) => void;
  onOpenSession?: (runId: number) => void;
}) {
  const [n, setN] = React.useState<NodeDetail | null>(null);
  React.useEffect(() => {
    setN(null);
    if (nodeId === null) return;
    api
      .node(nodeId)
      .then(setN)
      .catch((e) => toast.error((e as Error).message));
  }, [nodeId]);

  const meta = n ? (typeMeta[n.kind as keyof typeof typeMeta] ?? typeMeta.intent) : null;
  const Icon = meta?.icon;
  const p = n?.payload ?? {};
  const str = (k: string) => (typeof p[k] === "string" ? (p[k] as string) : "");

  return (
    <Sheet open={nodeId !== null} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="flex w-full flex-col gap-0 p-0 data-[side=right]:sm:max-w-lg">
        {!n || !meta || !Icon ? (
          <Loading className="h-full" />
        ) : (
          <>
            <SheetHeader className="border-b p-4">
              <div className="flex items-center gap-2.5 pr-8">
                <span className={cn("flex size-8 shrink-0 items-center justify-center rounded-lg shadow-sm", meta.iconBg)}>
                  <Icon className="size-4 text-white" />
                </span>
                <div className="min-w-0">
                  <SheetTitle className="leading-tight">
                    {meta.label} #{n.id}
                  </SheetTitle>
                  <SheetDescription className="text-xs">
                    {n.origin ? t("by {who}", { who: n.origin }) : ""} · {fmtTime(n.created_at)}
                  </SheetDescription>
                </div>
                <StatusBadge
                  domain={n.kind === "goal" ? "goal" : n.kind === "intent" ? "intent" : "node"}
                  value={n.state}
                  dot
                  className="ml-auto"
                />
              </div>
            </SheetHeader>
            <div className="flex-1 space-y-4 overflow-y-auto p-4">
              <p className="whitespace-pre-wrap text-sm">{str("summary") || str("text")}</p>
              <div className="divide-y">
                {str("platform") && <Row label={t("Platform")}>{platformLabel(str("platform"))}</Row>}
                {n.owner && <Row label={t("Worker")}>{n.owner}</Row>}
                {n.kind === "goal" && (
                  <Row label={t("Target")}>
                    {String(p.target_count ?? "—")} {String(p.min_intent ?? "")}+
                  </Row>
                )}
                {str("detail") && <Row label={t("Detail")}>{str("detail")}</Row>}
                {str("evidence") && <Row label={t("Evidence")}>{str("evidence")}</Row>}
                {str("confidence") && <Row label={t("Confidence")}>{str("confidence")}</Row>}
                <Row label={t("Derived from")}>
                  <Refs items={n.parents} onSelect={onSelect} />
                </Row>
                <Row label={t("Produced")}>
                  <Refs items={n.yields} onSelect={onSelect} />
                </Row>
                {n.sources.length > 0 && (
                  <Row label={t("Communities")}>
                    <div className="flex flex-col gap-1">
                      {n.sources.map((s) => (
                        <span key={s.id} className="flex items-center gap-2">
                          <Badge variant="outline" className="text-[10px]">
                            {s.kind}
                          </Badge>
                          <ExtLink href={s.url} className="text-xs" icon={false}>
                            {s.key}
                          </ExtLink>
                        </span>
                      ))}
                    </div>
                  </Row>
                )}
              </div>

              {n.kind === "lead" && n.lead && (
                <div className="space-y-2 rounded-lg border p-3">
                  <div className="flex items-center gap-2">
                    <StatusBadge domain="level" value={n.lead.intent_level} dot />
                    <span className="font-medium text-sm">{n.lead.author}</span>
                    <span className="text-muted-foreground text-xs">{t("fit {s}", { s: n.lead.fit_score })}</span>
                  </div>
                  <blockquote className="border-l-2 border-primary pl-3 text-sm">“{n.lead.quote}”</blockquote>
                  {onOpenLead && (
                    <Button size="sm" variant="outline" onClick={() => onOpenLead(n.id)}>
                      <UserCheck />
                      {t("Open lead")}
                    </Button>
                  )}
                </div>
              )}

              {n.kind === "intent" && (
                <div className="space-y-2">
                  <div className="font-medium text-sm">{t("Worker report")}</div>
                  <div className="rounded-lg bg-muted/50 p-3">
                    <Markdown text={n.worker_output || ""} />
                  </div>
                  {n.runs && n.runs.length > 0 && onOpenSession && (
                    <div className="flex flex-wrap gap-2">
                      {n.runs.map((r) => (
                        <Button key={r.id} size="sm" variant="outline" onClick={() => onOpenSession(r.id)}>
                          <MessagesSquare />
                          {t("Session #{id}", { id: r.id })}
                          <span className="text-muted-foreground text-xs">
                            {num(r.input_tokens + r.output_tokens)} tok
                          </span>
                        </Button>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}
