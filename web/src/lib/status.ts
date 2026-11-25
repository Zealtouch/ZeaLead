// Centralised status → color/label semantics, reused across the whole app (same tones as ZeaLead).

import { t } from "@/i18n";

export type Tone = "neutral" | "blue" | "green" | "amber" | "red" | "rose" | "violet" | "slate";

export const toneClasses: Record<Tone, string> = {
  neutral: "bg-muted text-muted-foreground border-transparent",
  blue: "bg-blue-500/15 text-blue-600 dark:text-blue-400 border-blue-500/20",
  green: "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/20",
  amber: "bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/20",
  red: "bg-red-500/15 text-red-600 dark:text-red-400 border-red-500/20",
  // rose is the solid, high-emphasis fill used for "Hot".
  rose: "bg-rose-600 text-white border-rose-600 dark:bg-rose-600 dark:text-white",
  violet: "bg-violet-500/15 text-violet-600 dark:text-violet-400 border-violet-500/20",
  slate: "bg-slate-500/15 text-slate-600 dark:text-slate-400 border-slate-500/20",
};

export const toneDot: Record<Tone, string> = {
  neutral: "bg-muted-foreground",
  blue: "bg-blue-500",
  green: "bg-emerald-500",
  amber: "bg-amber-500",
  red: "bg-red-500",
  rose: "bg-white",
  violet: "bg-violet-500",
  slate: "bg-slate-500",
};

interface StatusMeta {
  label: string;
  tone: Tone;
}

const intent: Record<string, StatusMeta> = {
  open: { label: t("Open"), tone: "slate" },
  running: { label: t("Running"), tone: "blue" },
  done: { label: t("Completed"), tone: "green" },
  // blocked = API/network failures; the intent barely explored anything.
  blocked: { label: t("Error"), tone: "red" },
  // exhausted = the turn budget cut the run short; partial results were written back.
  exhausted: { label: t("Budget exhausted"), tone: "violet" },
  stopped: { label: t("Stopped"), tone: "slate" },
};

const task: Record<string, StatusMeta> = {
  created: { label: t("Created"), tone: "slate" },
  running: { label: t("Running"), tone: "blue" },
  paused: { label: t("Paused"), tone: "amber" },
  done: { label: t("Completed"), tone: "green" },
  failed: { label: t("Failed"), tone: "red" },
  stopped: { label: t("Stopped"), tone: "slate" },
};

const level: Record<string, StatusMeta> = {
  hot: { label: t("Hot"), tone: "rose" },
  warm: { label: t("Warm"), tone: "amber" },
  cold: { label: t("Cold"), tone: "slate" },
};

const lead: Record<string, StatusMeta> = {
  new: { label: t("New"), tone: "blue" },
  contacted: { label: t("Contacted"), tone: "violet" },
  replied: { label: t("Replied"), tone: "amber" },
  won: { label: t("Won"), tone: "green" },
  dismissed: { label: t("Dismissed"), tone: "neutral" },
};

const goal: Record<string, StatusMeta> = {
  open: { label: t("In progress"), tone: "blue" },
  met: { label: t("Met"), tone: "green" },
  abandoned: { label: t("Abandoned"), tone: "slate" },
};

const run: Record<string, StatusMeta> = {
  running: { label: t("Live"), tone: "blue" },
  done: { label: t("Done"), tone: "green" },
  exhausted: { label: t("Budget exhausted"), tone: "violet" },
  error: { label: t("Error"), tone: "red" },
  stopped: { label: t("Stopped"), tone: "slate" },
};

const node: Record<string, StatusMeta> = {
  confirmed: { label: t("Confirmed"), tone: "green" },
  dismissed: { label: t("Dismissed"), tone: "neutral" },
  active: { label: t("Active"), tone: "violet" },
};

const role: Record<string, StatusMeta> = {
  admin: { label: t("Admin"), tone: "violet" },
  member: { label: t("Member"), tone: "slate" },
};

const maps = { intent, task, level, lead, goal, run, node, role } as const;

export type StatusDomain = keyof typeof maps;

export function statusMeta(domain: StatusDomain, key: string): StatusMeta {
  return maps[domain][key] ?? { label: t(key), tone: "neutral" };
}

export const PLATFORM_LABEL: Record<string, string> = {
  reddit: "Reddit",
  hackernews: "Hacker News",
  x: "X",
  bluesky: "Bluesky",
  stackexchange: "Stack Exchange",
  github: "GitHub",
  linkedin: "LinkedIn",
  g2: "G2",
  capterra: "Capterra",
  trustpilot: "Trustpilot",
  producthunt: "Product Hunt",
  quora: "Quora",
  indiehackers: "Indie Hackers",
  web: "Web",
};

export function platformLabel(p: string | null | undefined): string {
  if (!p) return "—";
  return PLATFORM_LABEL[p] ?? p;
}
