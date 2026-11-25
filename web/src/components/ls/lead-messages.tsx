"use client";

import * as React from "react";

import { MessageCircle, MessagesSquare, PenLine, RefreshCw, Save, Sparkles } from "lucide-react";
import { toast } from "sonner";

import { CopyButton } from "@/components/copy-button";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Spinner } from "@/components/ui/spinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { t } from "@/i18n";
import { api } from "@/lib/api";
import { ago } from "@/lib/format";
import { platformLabel } from "@/lib/status";
import type { LeadDetail } from "@/lib/types";

import { ExtLink } from "./ext-link";

type Kind = "suggested_reply" | "dm_message";

function Draft({
  lead,
  kind,
  onSaved,
}: {
  lead: LeadDetail;
  kind: Kind;
  onSaved: (l: LeadDetail) => void;
}) {
  const value = lead[kind] ?? "";
  const [text, setText] = React.useState(value);
  const [saving, setSaving] = React.useState(false);
  React.useEffect(() => setText(value), [value]);
  const dirty = text !== value;

  async function save() {
    setSaving(true);
    try {
      await api.editMessages(lead.node_id, { [kind]: text });
      onSaved({ ...lead, [kind]: text, message_edited: 1 });
      toast.success(t("Message saved"));
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  if (!value && !dirty) {
    return (
      <p className="rounded-lg border border-dashed p-3 text-muted-foreground text-sm">
        {lead.message_note
          ? t("Skipped: {why}", { why: lead.message_note })
          : t("No message for this channel.")}
      </p>
    );
  }

  const target =
    kind === "suggested_reply"
      ? { href: lead.url, label: t("Open the thread to reply") }
      : { href: lead.author_url, label: t("Open {who}'s profile", { who: lead.author || t("their") }) };

  return (
    <div className="space-y-2">
      <Textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={kind === "suggested_reply" ? 6 : 7}
        className="resize-y text-sm leading-relaxed"
        aria-label={kind === "suggested_reply" ? t("Public reply") : t("Direct message")}
      />
      <div className="flex flex-wrap items-center gap-2">
        <CopyButton text={text} label={t("Copy")} />
        {dirty && (
          <Button size="sm" variant="outline" onClick={save} disabled={saving}>
            <Save />
            {t("Save edit")}
          </Button>
        )}
        <span className="text-muted-foreground text-xs tabular-nums">{t("{n} characters", { n: text.length })}</span>
        <ExtLink href={target.href} className="ml-auto text-xs">
          {target.label}
        </ExtLink>
      </div>
    </div>
  );
}

// LeadMessages: the personalised public reply and direct message drafted for this one person
// from their own post. Editable; leadscout never sends them — a person copies and posts.
export function LeadMessages({ lead, onChange }: { lead: LeadDetail; onChange: (l: LeadDetail) => void }) {
  const [busy, setBusy] = React.useState(false);
  const [instruction, setInstruction] = React.useState("");
  const [rewriting, setRewriting] = React.useState(false);
  const drafted = !!lead.drafted_at;

  async function draft(withInstruction?: string) {
    setBusy(true);
    try {
      const l = await api.draftLead(lead.node_id, withInstruction);
      onChange(l);
      setInstruction("");
      setRewriting(false);
      toast.success(drafted ? t("Messages rewritten") : t("Messages drafted"));
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3 rounded-lg border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Sparkles className="size-4 text-violet-500" />
        <span className="font-medium text-sm">{t("Personal messages")}</span>
        {lead.message_edited ? (
          <Badge variant="secondary" className="text-[10px]">
            <PenLine />
            {t("edited")}
          </Badge>
        ) : null}
        {drafted && <span className="text-muted-foreground text-xs">{t("drafted {when}", { when: ago(lead.drafted_at) })}</span>}
        {drafted && (
          <Button
            size="sm"
            variant="ghost"
            className="ml-auto"
            onClick={() => setRewriting((v) => !v)}
            disabled={busy}
          >
            <RefreshCw />
            {t("Rewrite")}
          </Button>
        )}
      </div>

      {lead.message_angle && (
        <p className="text-muted-foreground text-xs">
          <span className="font-medium text-foreground">{t("Hook:")}</span> {lead.message_angle}
        </p>
      )}

      {!drafted ? (
        <div className="flex flex-col items-start gap-2 rounded-lg bg-muted/40 p-3 text-sm">
          <p className="text-muted-foreground">
            {t("Draft a public reply and a direct message written around what this person said.")}
          </p>
          <Button size="sm" onClick={() => draft()} disabled={busy}>
            {busy ? <Spinner /> : <Sparkles />}
            {t("Draft messages")}
          </Button>
        </div>
      ) : (
        <Tabs defaultValue={lead.dm_message ? "dm" : "reply"}>
          <TabsList>
            <TabsTrigger value="reply">
              <MessagesSquare />
              {t("Public reply")}
            </TabsTrigger>
            <TabsTrigger value="dm">
              <MessageCircle />
              {t("Direct message")}
            </TabsTrigger>
          </TabsList>
          <TabsContent value="reply" className="mt-2 space-y-1">
            <p className="text-muted-foreground text-xs">
              {t("A comment under their post on {p}. Others will see it.", { p: platformLabel(lead.platform) })}
            </p>
            <Draft lead={lead} kind="suggested_reply" onSaved={onChange} />
          </TabsContent>
          <TabsContent value="dm" className="mt-2 space-y-1">
            <p className="text-muted-foreground text-xs">{t("A private message to them (DM, LinkedIn message or email).")}</p>
            <Draft lead={lead} kind="dm_message" onSaved={onChange} />
          </TabsContent>
        </Tabs>
      )}

      {rewriting && (
        <form
          className="flex gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            void draft(instruction.trim() || undefined);
          }}
        >
          <Input
            value={instruction}
            maxLength={500}
            onChange={(e) => setInstruction(e.target.value)}
            placeholder={t("Optional: shorter, more formal, mention the free trial…")}
            className="h-8 text-sm"
          />
          <Button size="sm" type="submit" disabled={busy}>
            {busy ? <Spinner /> : <RefreshCw />}
            {t("Rewrite")}
          </Button>
        </form>
      )}
      {lead.message_edited && rewriting ? (
        <p className="text-amber-600 text-xs dark:text-amber-400">{t("Rewriting replaces your edits.")}</p>
      ) : null}
      <p className="text-muted-foreground text-[11px]">
        {t("Drafts only — review and send them yourself. Mass unsolicited messages break platform rules.")}
      </p>
    </div>
  );
}
