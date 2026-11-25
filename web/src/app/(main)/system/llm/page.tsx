"use client";

import { CheckCircle2, KeyRound, ShieldCheck, XCircle } from "lucide-react";

import { Loading } from "@/components/ls/loading";
import { PageHeader } from "@/components/ls/page-header";
import { EFFORTS, type FieldSpec, SettingsForm } from "@/components/ls/settings-form";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { usePoll } from "@/hooks/use-poll";
import { t } from "@/i18n";
import { api } from "@/lib/api";

const FIELDS: FieldSpec[] = [
  {
    key: "planner_model",
    label: t("Planner model"),
    hint: t("Runs the goal decomposer and every planning round. Use your strongest model."),
    type: "text",
  },
  {
    key: "planner_effort",
    label: t("Planner effort"),
    hint: t("How hard the planner thinks before dispatching intents."),
    type: "select",
    options: EFFORTS,
  },
  {
    key: "worker_model",
    label: t("Worker model"),
    hint: t("Runs each search intent: reading threads and judging leads."),
    type: "text",
  },
  {
    key: "worker_effort",
    label: t("Worker effort"),
    hint: t("Lower effort makes workers cheaper and faster."),
    type: "select",
    options: EFFORTS,
  },
];

const WRITER_FIELDS: FieldSpec[] = [
  {
    key: "writer_model",
    label: t("Message writer model"),
    hint: t("Drafts the personal public reply and direct message for each lead."),
    type: "text",
  },
  {
    key: "writer_effort",
    label: t("Message writer effort"),
    hint: t("Low is usually enough for short messages."),
    type: "select",
    options: EFFORTS,
  },
  {
    key: "auto_draft",
    label: t("Draft automatically"),
    hint: t("Write messages for each new lead while a task runs. Off: only when you ask."),
    type: "select",
    options: [
      { value: "1", label: t("On — every new lead") },
      { value: "0", label: t("Off — on request") },
    ],
  },
];

export default function LLMPage() {
  const { data, reload } = usePoll(() => api.settings(), []);
  if (!data) return <Loading className="min-h-96" />;

  return (
    <div className="flex flex-1 flex-col gap-4 md:gap-6">
      <PageHeader title={t("LLM")} description={t("Models and reasoning effort for each agent role")} />

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <KeyRound className="size-4" />
              {t("Anthropic API key")}
            </CardTitle>
            <CardDescription>{t("Read from ANTHROPIC_API_KEY in the server environment (.env)")}</CardDescription>
          </CardHeader>
          <CardContent>
            {data.anthropic_configured ? (
              <span className="flex items-center gap-2 text-emerald-600 text-sm dark:text-emerald-400">
                <CheckCircle2 className="size-4" />
                {t("Configured")}
              </span>
            ) : (
              <span className="flex items-center gap-2 text-red-600 text-sm dark:text-red-400">
                <XCircle className="size-4" />
                {t("Missing — tasks can't start until it's set")}
              </span>
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <ShieldCheck className="size-4" />
              {t("Server-side fallbacks")}
            </CardTitle>
            <CardDescription>{t("Retries an overloaded model on a fallback model, server side (ZEALEAD_FALLBACKS)")}</CardDescription>
          </CardHeader>
          <CardContent className="text-sm">
            {data.fallbacks ? (
              <span className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400">
                <CheckCircle2 className="size-4" />
                {t("On")}
              </span>
            ) : (
              <span className="text-muted-foreground">{t("Off")}</span>
            )}
          </CardContent>
        </Card>
      </div>

      {!data.anthropic_configured && (
        <Alert variant="destructive">
          <XCircle />
          <AlertTitle>{t("No API key")}</AlertTitle>
          <AlertDescription>
            {t("Add ANTHROPIC_API_KEY to .env and restart (docker compose up -d). Keys are never stored in the database or shown here.")}
          </AlertDescription>
        </Alert>
      )}

      <SettingsForm
        title={t("Models")}
        description={t("Overrides apply to tasks started from now on; running tasks keep their settings.")}
        fields={FIELDS}
        data={data}
        onSaved={reload}
      />
      <SettingsForm
        title={t("Personal messages")}
        description={t("Each lead gets its own reply and DM, written from what that person posted. Counts toward the task's token budget.")}
        fields={WRITER_FIELDS}
        data={data}
        onSaved={reload}
      />
    </div>
  );
}
