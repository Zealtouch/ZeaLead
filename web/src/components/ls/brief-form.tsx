"use client";

import * as React from "react";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { t } from "@/i18n";
import { PLATFORM_LABEL } from "@/lib/status";
import type { Brief } from "@/lib/types";

export type BriefDraft = {
  name: string;
  product: string;
  url: string;
  description: string;
  ideal_customer: string;
  pain_points: string;
  competitors: string;
  keywords: string;
  objective: string;
  target_leads: string;
  recency_days: string;
  exclude_platforms: string[];
  notes: string;
  sender: string;
  tone: string;
  offer: string;
};

export const EMPTY_BRIEF: BriefDraft = {
  name: "",
  product: "",
  url: "",
  description: "",
  ideal_customer: "",
  pain_points: "",
  competitors: "",
  keywords: "",
  objective: "",
  target_leads: "30",
  recency_days: "30",
  exclude_platforms: [],
  notes: "",
  sender: "",
  tone: "",
  offer: "",
};

const list = (s: string) =>
  s
    .split(/[\n,]/)
    .map((x) => x.trim())
    .filter(Boolean);

export function draftFromBrief(b: Brief): BriefDraft {
  return {
    name: b.name ?? "",
    product: b.product ?? "",
    url: b.url ?? "",
    description: b.description ?? "",
    ideal_customer: b.ideal_customer ?? "",
    pain_points: (b.pain_points ?? []).join("\n"),
    competitors: (b.competitors ?? []).join(", "),
    keywords: (b.keywords ?? []).join("\n"),
    objective: b.objective ?? "",
    target_leads: String(b.target_leads ?? 30),
    recency_days: String(b.recency_days ?? 30),
    exclude_platforms: b.exclude_platforms ?? [],
    notes: b.notes ?? "",
    sender: b.outreach?.sender ?? "",
    tone: b.outreach?.tone ?? "",
    offer: b.outreach?.offer ?? "",
  };
}

export function briefFromDraft(d: BriefDraft, base: Partial<Brief> = {}): Partial<Brief> {
  return {
    ...base,
    name: d.name.trim() || d.product.trim(),
    product: d.product.trim(),
    url: d.url.trim() || undefined,
    description: d.description.trim(),
    ideal_customer: d.ideal_customer.trim(),
    pain_points: list(d.pain_points),
    competitors: list(d.competitors),
    keywords: list(d.keywords),
    objective: d.objective.trim() || undefined,
    target_leads: Number(d.target_leads) || 30,
    recency_days: Number(d.recency_days) || 30,
    exclude_platforms: d.exclude_platforms,
    notes: d.notes.trim() || undefined,
    outreach:
      d.sender.trim() || d.tone.trim() || d.offer.trim()
        ? {
            sender: d.sender.trim() || undefined,
            tone: d.tone.trim() || undefined,
            offer: d.offer.trim() || undefined,
          }
        : undefined,
  };
}

const EXCLUDABLE = ["reddit", "hackernews", "x", "bluesky", "stackexchange", "github", "linkedin"];

function Field({
  label,
  hint,
  required,
  children,
}: {
  label: string;
  hint?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <Label className="text-sm">
        {label}
        {required && <span className="text-destructive">*</span>}
      </Label>
      {children}
      {hint && <p className="text-muted-foreground text-xs">{hint}</p>}
    </div>
  );
}

export function BriefForm({
  value,
  onChange,
  disabled,
}: {
  value: BriefDraft;
  onChange: (v: BriefDraft) => void;
  disabled?: boolean;
}) {
  const set = (k: keyof BriefDraft) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
    onChange({ ...value, [k]: e.target.value });
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      <Field label={t("Product name")} required>
        <Input value={value.product} onChange={set("product")} disabled={disabled} placeholder="Acme Invoicing" />
      </Field>
      <Field label={t("Task name")} hint={t("Defaults to the product name")}>
        <Input value={value.name} onChange={set("name")} disabled={disabled} />
      </Field>
      <div className="sm:col-span-2">
        <Field label={t("What the product does")} required>
          <Textarea
            value={value.description}
            onChange={set("description")}
            disabled={disabled}
            rows={3}
            placeholder={t("Invoicing with automatic payment reminders for freelancers and small agencies.")}
          />
        </Field>
      </div>
      <div className="sm:col-span-2">
        <Field label={t("Ideal customer")} required hint={t("Role, company size, industry")}>
          <Textarea value={value.ideal_customer} onChange={set("ideal_customer")} disabled={disabled} rows={2} />
        </Field>
      </div>
      <Field label={t("Pain points")} hint={t("One per line")}>
        <Textarea value={value.pain_points} onChange={set("pain_points")} disabled={disabled} rows={3} />
      </Field>
      <Field label={t("Seed phrases")} hint={t("What people type when they have the problem; one per line")}>
        <Textarea value={value.keywords} onChange={set("keywords")} disabled={disabled} rows={3} />
      </Field>
      <Field label={t("Competitors")} hint={t("Comma-separated")}>
        <Input value={value.competitors} onChange={set("competitors")} disabled={disabled} />
      </Field>
      <Field label={t("Product URL")}>
        <Input value={value.url} onChange={set("url")} disabled={disabled} placeholder="https://" />
      </Field>
      <div className="sm:col-span-2">
        <Field label={t("Objective")} hint={t("e.g. find 40 warm or hot leads, at least 10 hot")}>
          <Input value={value.objective} onChange={set("objective")} disabled={disabled} />
        </Field>
      </div>
      <Field label={t("Target leads")} hint={t("Used when the objective names no number")}>
        <Input type="number" min={1} value={value.target_leads} onChange={set("target_leads")} disabled={disabled} />
      </Field>
      <Field label={t("Recency")} hint={t("Only posts newer than this many days")}>
        <Select
          value={value.recency_days}
          onValueChange={(v) => onChange({ ...value, recency_days: v })}
          disabled={disabled}
        >
          <SelectTrigger className="w-full">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {Array.from(new Set(["7", "14", "30", "60", "90", "180", value.recency_days]))
              .filter(Boolean)
              .sort((a, b) => Number(a) - Number(b))
              .map((d) => (
              <SelectItem key={d} value={d}>
                {t("{d} days", { d })}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </Field>
      <div className="sm:col-span-2">
        <Field label={t("Never use these platforms")}>
          <div className="flex flex-wrap gap-2">
            {EXCLUDABLE.map((p) => {
              const on = value.exclude_platforms.includes(p);
              return (
                <button
                  key={p}
                  type="button"
                  disabled={disabled}
                  onClick={() =>
                    onChange({
                      ...value,
                      exclude_platforms: on ? value.exclude_platforms.filter((x) => x !== p) : [...value.exclude_platforms, p],
                    })
                  }
                  className={
                    on
                      ? "rounded-md border border-destructive/40 bg-destructive/10 px-2 py-1 text-destructive text-xs line-through"
                      : "rounded-md border px-2 py-1 text-xs hover:bg-muted"
                  }
                >
                  {PLATFORM_LABEL[p] ?? p}
                </button>
              );
            })}
          </div>
        </Field>
      </div>
      <div className="sm:col-span-2">
        <Field label={t("Rules for the agents")} hint={t("e.g. B2B only; no students; skip r/entrepreneur")}>
          <Textarea value={value.notes} onChange={set("notes")} disabled={disabled} rows={2} />
        </Field>
      </div>
      <div className="sm:col-span-2 border-t pt-4">
        <p className="font-medium text-sm">{t("Personal messages")}</p>
        <p className="text-muted-foreground text-xs">
          {t("Every lead gets a public reply and a direct message written around their own post. Optional:")}
        </p>
      </div>
      <Field label={t("Sender")} hint={t("Who signs the messages")}>
        <Input value={value.sender} onChange={set("sender")} disabled={disabled} placeholder={t("Sam, founder of Acme")} />
      </Field>
      <Field label={t("Tone")}>
        <Input value={value.tone} onChange={set("tone")} disabled={disabled} placeholder={t("friendly, plain, no hype")} />
      </Field>
      <div className="sm:col-span-2">
        <Field label={t("Offer")} hint={t("Only what you really offer; the writer never invents one")}>
          <Input value={value.offer} onChange={set("offer")} disabled={disabled} placeholder={t("a free 30-day trial")} />
        </Field>
      </div>
    </div>
  );
}
