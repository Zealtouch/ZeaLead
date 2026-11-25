"use client";

import { CheckCircle2, CircleSlash, Plug } from "lucide-react";

import { Loading } from "@/components/ls/loading";
import { PageHeader } from "@/components/ls/page-header";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { usePoll } from "@/hooks/use-poll";
import { t } from "@/i18n";
import { api } from "@/lib/api";
import { pretty } from "@/lib/format";

// Platforms: every connector, whether it's usable with the current .env, and the
// search tools it gives workers.
export default function PlatformsPage() {
  const { data } = usePoll(() => api.platforms(), []);
  if (!data) return <Loading className="min-h-96" />;
  const on = data.filter((p) => p.enabled).length;

  return (
    <div className="flex flex-1 flex-col gap-4 md:gap-6">
      <PageHeader
        title={t("Platforms")}
        description={t("{on} of {n} connectors enabled. Keyed connectors turn on when their keys are in .env.", {
          on,
          n: data.length,
        })}
      />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {data.map((p) => (
          <Card key={p.platform} className={p.enabled ? undefined : "opacity-80"}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <span className="flex size-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Plug className="size-4" />
                </span>
                {p.label}
                {p.enabled ? (
                  <Badge variant="outline" className="ml-auto border-emerald-500/30 text-emerald-600 dark:text-emerald-400">
                    <CheckCircle2 />
                    {t("Enabled")}
                  </Badge>
                ) : (
                  <Badge variant="outline" className="ml-auto text-muted-foreground">
                    <CircleSlash />
                    {t("Disabled")}
                  </Badge>
                )}
              </CardTitle>
              <CardDescription>{p.doc}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {!p.enabled && p.missing && (
                <p className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-3 py-2 text-amber-700 text-xs dark:text-amber-400">
                  {p.missing}
                </p>
              )}
              <Accordion type="single" collapsible>
                <AccordionItem value="tools" className="border-b-0">
                  <AccordionTrigger className="py-2 text-sm">{t("{n} tools", { n: p.tools.length })}</AccordionTrigger>
                  <AccordionContent className="space-y-2">
                    {p.tools.map((tl) => (
                      <div key={tl.name} className="rounded-lg border px-3 py-2">
                        <div className="font-medium font-mono text-xs">{tl.name}</div>
                        <div className="text-muted-foreground text-xs">{tl.description}</div>
                        <details className="mt-1">
                          <summary className="cursor-pointer text-muted-foreground text-[11px]">{t("Input schema")}</summary>
                          <pre className="mt-1 max-h-48 overflow-auto rounded bg-muted/50 p-2 font-mono text-[10px]">
                            {pretty(tl.schema)}
                          </pre>
                        </details>
                      </div>
                    ))}
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
