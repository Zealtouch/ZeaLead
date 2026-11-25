"use client";

// Roles tab: which model profile and effort each agent role uses.
//
// A role left on "Active profile" follows the starred profile and joins the failover pool; a role pinned
// to a profile uses only that profile (unless "also fall back when a pinned profile fails" is on).
// With no profiles at all, roles use the .env Anthropic key and the model names set here.

import * as React from "react";

import { Compass, Loader2Icon, PenLine, Radio, RotateCcw, SaveIcon } from "lucide-react";
import { toast } from "sonner";

import { EFFORTS } from "@/components/ls/settings-form";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useCurrentUser } from "@/hooks/use-current-user";
import { t } from "@/i18n";
import { api } from "@/lib/api";
import type { LLMProfile, SettingsResp } from "@/lib/types";

const ACTIVE = "active"; // Radix Select rejects "", so the UI uses this sentinel for "no pin"

type Role = {
  key: string;
  title: string;
  who: string;
  icon: React.ElementType;
  profile: string;
  effort: string;
  model: string;
};

const ROLES: Role[] = [
  {
    key: "planner",
    title: t("Planner + goal decomposer"),
    who: t("Turns the brief into goals and plans every round. Use your strongest model."),
    icon: Compass,
    profile: "planner_profile",
    effort: "planner_effort",
    model: "planner_model",
  },
  {
    key: "worker",
    title: t("Workers"),
    who: t("Run each search intent: read threads and judge leads. Most of the token spend."),
    icon: Radio,
    profile: "worker_profile",
    effort: "worker_effort",
    model: "worker_model",
  },
  {
    key: "writer",
    title: t("Message writer"),
    who: t("Drafts the personal reply and DM for each lead. Short output: a cheaper model works."),
    icon: PenLine,
    profile: "writer_profile",
    effort: "writer_effort",
    model: "writer_model",
  },
];

export function RolesPanel({
  settings,
  profiles,
  onSaved,
}: {
  settings: SettingsResp;
  profiles: LLMProfile[];
  onSaved: () => void;
}) {
  const canEdit = useCurrentUser().role === "admin";
  const keys = React.useMemo(() => [...ROLES.flatMap((r) => [r.profile, r.effort, r.model]), "auto_draft"], []);
  const initial = React.useMemo(
    () => Object.fromEntries(keys.map((k) => [k, String(settings.values[k] ?? "")])),
    [keys, settings],
  );
  const [form, setForm] = React.useState(initial);
  const [saving, setSaving] = React.useState(false);
  React.useEffect(() => setForm(initial), [initial]);
  const dirty = keys.filter((k) => form[k] !== initial[k]);
  const active = profiles.find((p) => p.is_default) ?? profiles[0];
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  async function save(body: Record<string, string | number | null>, msg: string) {
    setSaving(true);
    try {
      await api.saveSettings(body);
      toast.success(msg);
      onSaved();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="grid gap-4">
      <div className="rounded-lg border bg-muted/30 p-3 text-muted-foreground text-xs leading-relaxed">
        {profiles.length
          ? t(
              "A role on “Active profile” follows the starred profile and, with the pool on, fails over to the others. A pinned role uses only its profile. Effort applies to profiles whose effort is “Follow the role”.",
            )
          : t(
              "No model profiles yet: every role uses ANTHROPIC_API_KEY from .env with the model names below. Once you create a profile, roles use profiles instead.",
            )}
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {ROLES.map((r) => {
          const Icon = r.icon;
          const pin = form[r.profile] || ACTIVE;
          const pinned = profiles.find((p) => p.id === form[r.profile]);
          const used = pinned ?? active;
          return (
            <Card key={r.key}>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <span className="flex size-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
                    <Icon className="size-4" />
                  </span>
                  {r.title}
                </CardTitle>
                <CardDescription>{r.who}</CardDescription>
              </CardHeader>
              <CardContent className="grid gap-4">
                {profiles.length > 0 ? (
                  <div className="grid gap-1.5">
                    <Label htmlFor={`r-${r.key}-p`}>{t("Model profile")}</Label>
                    <Select value={pin} onValueChange={(v) => set(r.profile, v === ACTIVE ? "" : v)} disabled={!canEdit}>
                      <SelectTrigger id={`r-${r.key}-p`} className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value={ACTIVE}>{t("Active profile ({name})", { name: active?.name ?? "—" })}</SelectItem>
                        {profiles.map((p) => (
                          <SelectItem key={p.id} value={p.id}>
                            {p.name} · {p.model}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {used && (
                      <p className="flex flex-wrap items-center gap-1.5 text-muted-foreground text-xs">
                        <Badge variant="outline" className="uppercase" lang="en">
                          {used.format}
                        </Badge>
                        <code className="font-mono">{used.model}</code>
                        {pinned ? t("· pinned") : t("· joins the pool")}
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="grid gap-1.5">
                    <Label htmlFor={`r-${r.key}-m`}>{t("Model (environment key)")}</Label>
                    <Input
                      id={`r-${r.key}-m`}
                      className="font-mono text-sm"
                      value={form[r.model]}
                      disabled={!canEdit}
                      onChange={(e) => set(r.model, e.target.value)}
                    />
                  </div>
                )}
                <div className="grid gap-1.5">
                  <Label htmlFor={`r-${r.key}-e`}>{t("Effort")}</Label>
                  <Select value={form[r.effort]} onValueChange={(v) => set(r.effort, v)} disabled={!canEdit}>
                    <SelectTrigger id={`r-${r.key}-e`} className="w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {EFFORTS.map((o) => (
                        <SelectItem key={o.value} value={o.value}>
                          {o.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {used && used.reasoning_effort !== "role" && (
                    <p className="text-amber-600 text-xs dark:text-amber-400">
                      {t("Profile “{name}” sets its own effort ({e}), which wins over this.", {
                        name: used.name,
                        e: used.reasoning_effort || t("not sent"),
                      })}
                    </p>
                  )}
                </div>
                {r.key === "writer" && (
                  <div className="grid gap-1.5">
                    <Label htmlFor="r-auto-draft">{t("Draft automatically")}</Label>
                    <Select value={form.auto_draft} onValueChange={(v) => set("auto_draft", v)} disabled={!canEdit}>
                      <SelectTrigger id="r-auto-draft" className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="1">{t("On — every new lead")}</SelectItem>
                        <SelectItem value="0">{t("Off — on request")}</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                )}
              </CardContent>
            </Card>
          );
        })}
      </div>

      {canEdit ? (
        <div className="flex flex-wrap justify-end gap-2">
          <Button
            variant="outline"
            disabled={saving || !keys.some((k) => settings.overrides[k] !== undefined)}
            onClick={() => save(Object.fromEntries(keys.map((k) => [k, null])), t("Roles reset to the environment defaults"))}
          >
            <RotateCcw />
            {t("Reset to environment")}
          </Button>
          <Button
            disabled={saving || dirty.length === 0}
            onClick={() =>
              save(
                Object.fromEntries(dirty.map((k) => [k, k === "auto_draft" ? Number(form[k]) : form[k] || null])),
                t("Saved — pins apply to the next model call; models and efforts to tasks started from now on"),
              )
            }
          >
            {saving ? <Loader2Icon className="animate-spin" /> : <SaveIcon />}
            {t("Save")}
          </Button>
        </div>
      ) : (
        <p className="text-muted-foreground text-xs">{t("Only admins can change settings.")}</p>
      )}
    </div>
  );
}
