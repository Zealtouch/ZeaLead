"use client";

import * as React from "react";

import { RotateCcw, Save } from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useCurrentUser } from "@/hooks/use-current-user";
import { t } from "@/i18n";
import { api } from "@/lib/api";
import type { SettingsResp } from "@/lib/types";

export type FieldSpec = {
  key: string;
  label: string;
  hint: string;
  type: "text" | "number" | "select";
  options?: { value: string; label: string }[];
  min?: number;
};

// SettingsForm edits a group of console-editable settings (leadscout/config.py EDITABLE).
// Overrides live in the database and apply to tasks started afterwards; clearing a field
// falls back to the environment value. Members see the values read-only.
export function SettingsForm({
  title,
  description,
  fields,
  data,
  onSaved,
}: {
  title: string;
  description: string;
  fields: FieldSpec[];
  data: SettingsResp;
  onSaved: () => void;
}) {
  const user = useCurrentUser();
  const admin = user.role === "admin";
  const initial = React.useMemo(
    () => Object.fromEntries(fields.map((f) => [f.key, String(data.values[f.key] ?? "")])),
    [fields, data],
  );
  const [vals, setVals] = React.useState<Record<string, string>>(initial);
  const [saving, setSaving] = React.useState(false);
  React.useEffect(() => setVals(initial), [initial]);
  const dirty = fields.some((f) => vals[f.key] !== initial[f.key]);

  async function save(body: Record<string, string | number | null>) {
    setSaving(true);
    try {
      const r = await api.saveSettings(body);
      toast.success(t("Saved — {note}", { note: r.note }));
      onSaved();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
        <CardDescription>{description}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-5 sm:grid-cols-2">
          {fields.map((f) => (
            <div key={f.key} className="flex flex-col gap-1.5">
              <Label htmlFor={`s-${f.key}`} className="flex items-center gap-2">
                {f.label}
                {data.overrides[f.key] !== undefined && (
                  <Badge variant="secondary" className="h-4 px-1 text-[10px]">
                    {t("override")}
                  </Badge>
                )}
              </Label>
              {f.type === "select" ? (
                <Select value={vals[f.key]} onValueChange={(v) => setVals({ ...vals, [f.key]: v })} disabled={!admin}>
                  <SelectTrigger id={`s-${f.key}`} className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {f.options?.map((o) => (
                      <SelectItem key={o.value} value={o.value}>
                        {o.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              ) : (
                <Input
                  id={`s-${f.key}`}
                  type={f.type}
                  min={f.min}
                  value={vals[f.key]}
                  disabled={!admin}
                  onChange={(e) => setVals({ ...vals, [f.key]: e.target.value })}
                  className={f.type === "text" ? "font-mono text-sm" : "tabular-nums"}
                />
              )}
              <p className="text-muted-foreground text-xs">{f.hint}</p>
            </div>
          ))}
        </div>
        {admin ? (
          <div className="flex flex-wrap justify-end gap-2">
            <Button
              variant="outline"
              disabled={saving || !fields.some((f) => data.overrides[f.key] !== undefined)}
              onClick={() => save(Object.fromEntries(fields.map((f) => [f.key, null])))}
            >
              <RotateCcw />
              {t("Reset to environment")}
            </Button>
            <Button
              disabled={saving || !dirty}
              onClick={() =>
                save(
                  Object.fromEntries(
                    fields
                      .filter((f) => vals[f.key] !== initial[f.key])
                      .map((f) => [f.key, f.type === "number" ? Number(vals[f.key]) : vals[f.key]]),
                  ),
                )
              }
            >
              <Save />
              {t("Save")}
            </Button>
          </div>
        ) : (
          <p className="text-muted-foreground text-xs">{t("Only admins can change settings.")}</p>
        )}
      </CardContent>
    </Card>
  );
}

export const EFFORTS = ["low", "medium", "high", "xhigh", "max"].map((v) => ({ value: v, label: v }));
