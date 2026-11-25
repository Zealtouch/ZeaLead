"use client";

import * as React from "react";

import { Lock, Save } from "lucide-react";
import { toast } from "sonner";

import { BriefForm, briefFromDraft, draftFromBrief } from "@/components/ls/brief-form";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { usePoll } from "@/hooks/use-poll";
import { t } from "@/i18n";
import { api } from "@/lib/api";
import type { TaskDetail } from "@/lib/types";

// Brief: what the agents are told about the product. Editable while the task isn't running;
// the planner reads the new brief on the next start.
export function BriefTab({ task, onSaved }: { task: TaskDetail; onSaved: () => void }) {
  const locked = task.status === "running";
  const [draft, setDraft] = React.useState(() => draftFromBrief(task.brief));
  const [saving, setSaving] = React.useState(false);
  const { data: companies } = usePoll(() => api.companies(), []);
  const dirty = JSON.stringify(draft) !== JSON.stringify(draftFromBrief(task.brief));

  React.useEffect(() => {
    setDraft(draftFromBrief(task.brief));
  }, [task.brief]);

  async function save() {
    setSaving(true);
    try {
      await api.updateBrief(task.id, { brief: briefFromDraft(draft, task.brief) });
      toast.success(t("Brief saved"));
      onSaved();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function setCompany(v: string) {
    try {
      await api.setTaskCompany(task.id, v === "none" ? null : Number(v));
      toast.success(t("Company updated"));
      onSaved();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
      <Card>
        <CardHeader>
          <CardTitle>{t("Product brief")}</CardTitle>
          <CardDescription>{t("Everything the decomposer, planner and workers know about your product")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {locked && (
            <Alert>
              <Lock />
              <AlertDescription>{t("Pause the task to edit its brief.")}</AlertDescription>
            </Alert>
          )}
          <BriefForm value={draft} onChange={setDraft} disabled={locked} />
          <div className="flex justify-end gap-2">
            <Button variant="outline" disabled={!dirty || saving} onClick={() => setDraft(draftFromBrief(task.brief))}>
              {t("Discard")}
            </Button>
            <Button
              disabled={locked || !dirty || saving || !draft.product.trim() || !draft.description.trim()}
              onClick={save}
            >
              <Save />
              {t("Save brief")}
            </Button>
          </div>
        </CardContent>
      </Card>
      <Card className="h-fit">
        <CardHeader>
          <CardTitle>{t("Company")}</CardTitle>
          <CardDescription>{t("Group tasks by the company or product line they belong to")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <Label className="sr-only">{t("Company")}</Label>
          <Select value={task.company_id ? String(task.company_id) : "none"} onValueChange={setCompany}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">{t("No company")}</SelectItem>
              {(companies ?? []).map((c) => (
                <SelectItem key={c.id} value={String(c.id)}>
                  {c.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardContent>
      </Card>
    </div>
  );
}
