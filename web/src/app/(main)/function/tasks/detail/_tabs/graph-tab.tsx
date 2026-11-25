"use client";

import * as React from "react";

import { ExplorationGraph } from "@/components/ls/exploration-graph";
import { LeadSheet } from "@/components/ls/lead-sheet";
import { Loading } from "@/components/ls/loading";
import { NodeSheet } from "@/components/ls/node-sheet";
import { Card } from "@/components/ui/card";
import { usePoll } from "@/hooks/use-poll";
import { t } from "@/i18n";
import { api } from "@/lib/api";
import type { TaskDetail } from "@/lib/types";

// Exploration graph: goals → intents → facts/leads, refreshed every 5 s while the task runs.
export function GraphTab({ task, onOpenSession }: { task: TaskDetail; onOpenSession: (runId: number) => void }) {
  const { data } = usePoll(() => api.graph(task.id), [task.id], task.status === "running" ? 5000 : 0);
  const [node, setNode] = React.useState<number | null>(null);
  const [lead, setLead] = React.useState<number | null>(null);

  if (!data) return <Loading className="min-h-96" />;

  return (
    <Card className="h-[calc(100dvh-10.5rem)] min-h-[520px] overflow-hidden py-0">
      {data.nodes.length === 0 ? (
        <div className="flex h-full items-center justify-center text-muted-foreground text-sm">
          {t("The graph fills in as the planner creates goals and intents.")}
        </div>
      ) : (
        <ExplorationGraph nodes={data.nodes} edges={data.edges} selectedId={node} onSelect={setNode} />
      )}
      <NodeSheet
        nodeId={node}
        onOpenChange={(o) => !o && setNode(null)}
        onSelect={setNode}
        onOpenLead={(id) => {
          setNode(null);
          setLead(id);
        }}
        onOpenSession={(id) => {
          setNode(null);
          onOpenSession(id);
        }}
      />
      <LeadSheet leadId={lead} onOpenChange={(o) => !o && setLead(null)} />
    </Card>
  );
}
