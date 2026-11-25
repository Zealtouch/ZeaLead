"use client";

import { useState } from "react";

import Link from "next/link";

import { Building2, Pencil, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { Confirm } from "@/components/ls/confirm";
import { ExtLink } from "@/components/ls/ext-link";
import { EmptyRow, Loading } from "@/components/ls/loading";
import { PageHeader } from "@/components/ls/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { usePoll } from "@/hooks/use-poll";
import { t } from "@/i18n";
import { api } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { Company } from "@/lib/types";
import { useCompanyStore } from "@/stores/company/company-store";

type Draft = { name: string; website: string; description: string };

function CompanyDialog({
  company,
  open,
  onOpenChange,
  onSaved,
}: {
  company: Company | null;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onSaved: () => void;
}) {
  const [d, setD] = useState<Draft>({ name: "", website: "", description: "" });
  const [saving, setSaving] = useState(false);
  const [lastOpen, setLastOpen] = useState(false);
  if (open !== lastOpen) {
    setLastOpen(open);
    if (open) setD({ name: company?.name ?? "", website: company?.website ?? "", description: company?.description ?? "" });
  }

  async function save() {
    setSaving(true);
    const body = { name: d.name.trim(), website: d.website.trim() || undefined, description: d.description.trim() || undefined };
    try {
      if (company) await api.updateCompany(company.id, body);
      else await api.createCompany(body);
      toast.success(company ? t("Company updated") : t("Company created"));
      onOpenChange(false);
      onSaved();
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{company ? t("Edit company") : t("New company")}</DialogTitle>
          <DialogDescription>{t("Companies group tasks and leads — one per product or client.")}</DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          <div className="grid gap-1.5">
            <Label htmlFor="c-name">{t("Name")}</Label>
            <Input id="c-name" value={d.name} onChange={(e) => setD({ ...d, name: e.target.value })} maxLength={120} />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="c-web">{t("Website")}</Label>
            <Input
              id="c-web"
              value={d.website}
              placeholder="https://example.com"
              onChange={(e) => setD({ ...d, website: e.target.value })}
            />
          </div>
          <div className="grid gap-1.5">
            <Label htmlFor="c-desc">{t("Description")}</Label>
            <Textarea id="c-desc" rows={3} value={d.description} onChange={(e) => setD({ ...d, description: e.target.value })} />
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("Cancel")}
          </Button>
          <Button onClick={save} disabled={saving || !d.name.trim()}>
            {t("Save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function CompaniesPage() {
  const { data, loading, reload } = usePoll(() => api.companies(), []);
  const [editing, setEditing] = useState<Company | null>(null);
  const [dialog, setDialog] = useState(false);
  const [deleting, setDeleting] = useState<Company | null>(null);
  const setActive = useCompanyStore((s) => s.setCompany);
  const activeId = useCompanyStore((s) => s.companyId);

  async function remove(c: Company) {
    try {
      await api.deleteCompany(c.id);
      if (activeId === c.id) setActive(null);
      toast.success(t("Company deleted"));
      reload();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <div className="flex flex-1 flex-col gap-4 md:gap-6">
      <PageHeader
        title={t("Companies")}
        description={t("Products or clients you find customers for. Switch between them from the sidebar.")}
        actions={
          <Button
            size="sm"
            onClick={() => {
              setEditing(null);
              setDialog(true);
            }}
          >
            <Plus />
            {t("New company")}
          </Button>
        }
      />
      <Card className="gap-0 py-0">
        <CardContent className="px-0">
          {loading && !data ? (
            <Loading />
          ) : !data?.length ? (
            <EmptyRow text={t("No companies yet. Create one to group tasks and leads.")} />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-4 lg:pl-6">{t("Company")}</TableHead>
                  <TableHead>{t("Website")}</TableHead>
                  <TableHead className="text-right">{t("Tasks")}</TableHead>
                  <TableHead className="text-right">{t("Leads")}</TableHead>
                  <TableHead>{t("Created")}</TableHead>
                  <TableHead className="pr-4 text-right lg:pr-6">{t("Actions")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.map((c) => (
                  <TableRow key={c.id}>
                    <TableCell className="pl-4 lg:pl-6">
                      <div className="flex items-center gap-2">
                        <span className="flex size-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
                          <Building2 className="size-4" />
                        </span>
                        <div className="min-w-0">
                          <div className="font-medium">{c.name}</div>
                          {c.description && <div className="line-clamp-1 max-w-md text-muted-foreground text-xs">{c.description}</div>}
                        </div>
                      </div>
                    </TableCell>
                    <TableCell>
                      <ExtLink href={c.website} className="text-sm" />
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      <Link
                        prefetch={false}
                        href="/function/tasks"
                        onClick={() => setActive(c.id, c.name)}
                        className="hover:underline"
                      >
                        {c.tasks}
                      </Link>
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      <Link
                        prefetch={false}
                        href="/function/leads"
                        onClick={() => setActive(c.id, c.name)}
                        className="hover:underline"
                      >
                        {c.leads}
                      </Link>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-xs">{fmtDate(c.created_at)}</TableCell>
                    <TableCell className="pr-4 text-right lg:pr-6">
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={t("Edit")}
                        onClick={() => {
                          setEditing(c);
                          setDialog(true);
                        }}
                      >
                        <Pencil />
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon-sm"
                        aria-label={t("Delete")}
                        className="text-destructive hover:text-destructive"
                        onClick={() => setDeleting(c)}
                      >
                        <Trash2 />
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <CompanyDialog company={editing} open={dialog} onOpenChange={setDialog} onSaved={reload} />
      <Confirm
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={t("Delete company?")}
        description={t("Its tasks and leads are kept and become unassigned. This can't be undone.")}
        onConfirm={() => deleting && remove(deleting)}
      />
    </div>
  );
}
