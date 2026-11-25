"use client";

import { Bot, Compass, PenLine, Radio, Target, Wrench } from "lucide-react";

import { Loading } from "@/components/ls/loading";
import { PageHeader } from "@/components/ls/page-header";
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { usePoll } from "@/hooks/use-poll";
import { t } from "@/i18n";
import { api } from "@/lib/api";

const ICON: Record<string, React.ElementType> = { decomposer: Target, planner: Compass, worker: Radio, writer: PenLine };

// Agent: the roles, their system prompts, tools and the model profile each one resolves to.
export default function AgentsPage() {
  const { data } = usePoll(() => api.agents(), []);
  if (!data) return <Loading className="min-h-96" />;

  return (
    <div className="flex flex-1 flex-col gap-4 md:gap-6">
      <PageHeader
        title={t("Agent")}
        description={t("Decomposer → planner → workers → message writer. Change models and limits in LLM and System Settings.")}
      />
      {data.map((a) => {
        const Icon = ICON[a.role] ?? Bot;
        return (
          <Card key={a.role}>
            <CardHeader>
              <CardTitle className="flex flex-wrap items-center gap-2">
                <span className="flex size-7 items-center justify-center rounded-lg bg-primary/10 text-primary">
                  <Icon className="size-4" />
                </span>
                {a.title}
                <Badge variant="outline" className="font-mono">
                  {a.model}
                </Badge>
                {a.profile && (
                  <Badge variant="secondary" title={a.format}>
                    {a.profile}
                  </Badge>
                )}
                <Badge variant="secondary">{t("effort {e}", { e: a.effort })}</Badge>
                <Badge variant="secondary">{t("{n} turns max", { n: a.max_turns })}</Badge>
                {a.count !== undefined && <Badge variant="secondary">{t("×{n} in parallel", { n: a.count })}</Badge>}
              </CardTitle>
              <CardDescription>{a.description}</CardDescription>
            </CardHeader>
            <CardContent>
              <Accordion type="multiple">
                <AccordionItem value="tools">
                  <AccordionTrigger>
                    <span className="flex items-center gap-2">
                      <Wrench className="size-4" />
                      {t("Tools ({n})", { n: a.tools.length })}
                    </span>
                  </AccordionTrigger>
                  <AccordionContent>
                    <div className="grid gap-2 md:grid-cols-2">
                      {a.tools.map((tl) => (
                        <div key={tl.name} className="rounded-lg border px-3 py-2">
                          <div className="font-medium font-mono text-xs">{tl.name}</div>
                          <div className="line-clamp-3 text-muted-foreground text-xs">{tl.description}</div>
                        </div>
                      ))}
                    </div>
                  </AccordionContent>
                </AccordionItem>
                <AccordionItem value="prompt">
                  <AccordionTrigger>{t("System prompt")}</AccordionTrigger>
                  <AccordionContent>
                    <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap rounded-lg bg-muted/50 p-3 font-mono text-[11px] leading-relaxed">
                      {a.system}
                    </pre>
                  </AccordionContent>
                </AccordionItem>
              </Accordion>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
