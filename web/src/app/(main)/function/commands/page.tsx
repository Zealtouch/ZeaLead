"use client";

import { PageHeader } from "@/components/ls/page-header";
import { ToolCallsView } from "@/components/ls/tool-calls-view";
import { t } from "@/i18n";

export default function CommandsPage() {
  return (
    <div className="flex flex-1 flex-col gap-4 md:gap-6">
      <PageHeader
        title={t("Tool Execution")}
        description={t("Every platform search, thread read and graph write the agents made — input, output and timing")}
      />
      <ToolCallsView />
    </div>
  );
}
