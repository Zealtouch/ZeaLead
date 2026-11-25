"use client";

import { Building2, Database, FolderKey, Info, Target, Users } from "lucide-react";

import { Loading } from "@/components/ls/loading";
import { PageHeader } from "@/components/ls/page-header";
import { type FieldSpec, SettingsForm } from "@/components/ls/settings-form";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { usePoll } from "@/hooks/use-poll";
import { t } from "@/i18n";
import { api } from "@/lib/api";

const RUN_FIELDS: FieldSpec[] = [
  { key: "workers", label: t("Parallel workers"), hint: t("Intents worked at the same time per task."), type: "number", min: 1 },
  {
    key: "budget_tokens",
    label: t("Token budget per task"),
    hint: t("The task stops cleanly once this many tokens are spent."),
    type: "number",
    min: 0,
  },
  { key: "intent_max_turns", label: t("Worker turn limit"), hint: t("Model turns one worker may spend on one intent."), type: "number", min: 1 },
  { key: "planner_max_turns", label: t("Planner turn limit"), hint: t("Model turns per planning round."), type: "number", min: 1 },
  {
    key: "heartbeat_seconds",
    label: t("Heartbeat (seconds)"),
    hint: t("The planner wakes at least this often, even with no graph change."),
    type: "number",
    min: 10,
  },
  {
    key: "stagnation_rounds",
    label: t("Stagnation rounds"),
    hint: t("Stop after this many planning rounds with no new leads."),
    type: "number",
    min: 1,
  },
];

const NOISE_FIELDS: FieldSpec[] = [
  {
    key: "noise_profile",
    label: t("Request pacing"),
    hint: t("How politely platforms are queried: per-host interval and concurrent requests."),
    type: "select",
    options: [
      { value: "quiet", label: t("Quiet — 3 s apart, 1 at a time") },
      { value: "balanced", label: t("Balanced — 1.2 s apart, 2 at a time") },
      { value: "aggressive", label: t("Aggressive — 0.4 s apart, 4 at a time") },
    ],
  },
];

function InfoRow({ icon: Icon, label, children }: { icon: React.ElementType; label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-3 py-2 text-sm">
      <Icon className="size-4 shrink-0 text-muted-foreground" />
      <span className="w-28 shrink-0 text-muted-foreground">{label}</span>
      <span className="min-w-0 flex-1 truncate font-mono text-xs">{children}</span>
    </div>
  );
}

export default function SettingsPage() {
  const { data, reload } = usePoll(() => api.settings(), []);
  const { data: info } = usePoll(() => api.systemInfo(), []);
  if (!data) return <Loading className="min-h-96" />;

  return (
    <div className="flex flex-1 flex-col gap-4 md:gap-6">
      <PageHeader title={t("System Settings")} description={t("Run limits, pacing and installation details")} />
      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <div className="flex flex-col gap-4">
          <SettingsForm
            title={t("Run limits")}
            description={t("Keep spend and runtime bounded. Applies to tasks started from now on.")}
            fields={RUN_FIELDS}
            data={data}
            onSaved={reload}
          />
          <SettingsForm
            title={t("Platform pacing")}
            description={t("ZeaLead reads public pages only and paces itself per host.")}
            fields={NOISE_FIELDS}
            data={data}
            onSaved={reload}
          />
        </div>
        <Card className="h-fit">
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Info className="size-4" />
              {t("System")}
            </CardTitle>
            <CardDescription>{t("This installation")}</CardDescription>
          </CardHeader>
          <CardContent className="divide-y">
            {!info ? (
              <Loading />
            ) : (
              <>
                <InfoRow icon={Info} label={t("Version")}>
                  {info.version}
                </InfoRow>
                <InfoRow icon={Info} label={t("Python")}>
                  {info.python}
                </InfoRow>
                <InfoRow icon={Database} label={t("Database")}>
                  {info.db_path}
                </InfoRow>
                <InfoRow icon={FolderKey} label={t("Keys dir")}>
                  {info.keys_dir}
                </InfoRow>
                <InfoRow icon={Building2} label={t("Companies")}>
                  {info.companies}
                </InfoRow>
                <InfoRow icon={Target} label={t("Tasks")}>
                  {info.tasks}
                </InfoRow>
                <InfoRow icon={Users} label={t("Users")}>
                  {info.users}
                </InfoRow>
                <InfoRow icon={Info} label={t("Console")}>
                  {info.webui ? <Badge variant="secondary">{t("bundled")}</Badge> : <Badge variant="outline">{t("dev server")}</Badge>}
                </InfoRow>
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
