"use client";

import { Suspense, useEffect, useMemo, useState } from "react";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";

import { Eye, Pause, Play, Plus, SearchIcon, Trash2 } from "lucide-react";
import { toast } from "sonner";

import { BriefForm, type BriefDraft, briefFromDraft, EMPTY_BRIEF } from "@/components/ls/brief-form";
import { Confirm } from "@/components/ls/confirm";
import { EmptyRow, Loading } from "@/components/ls/loading";
import { PageHeader } from "@/components/ls/page-header";
import { StatusBadge } from "@/components/status-badge";
import { TablePagination } from "@/components/table-pagination";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { InputGroup, InputGroupAddon, InputGroupInput } from "@/components/ui/input-group";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { usePoll } from "@/hooks/use-poll";
import { t } from "@/i18n";
import { api } from "@/lib/api";
import { fmtTime, num } from "@/lib/format";
import { statusMeta } from "@/lib/status";
import type { Company, Task } from "@/lib/types";
import { useActiveCompanyID } from "@/stores/company/company-store";

const STATUSES = ["created", "running", "paused", "done", "failed"];

function IconAction({
  label,
  onClick,
  children,
  destructive,
  disabled,
}: {
  label: string;
  onClick: () => void;
  children: React.ReactNode;
  destructive?: boolean;
  disabled?: boolean;
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          variant={destructive ? "outline" : "ghost"}
          size="icon-sm"
          onClick={onClick}
          disabled={disabled}
          aria-label={label}
          className={destructive ? "text-destructive hover:text-destructive" : undefined}
        >
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

function NewTaskDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onCreated: (id: number) => void;
}) {
  const activeCompany = useActiveCompanyID();
  const [mode, setMode] = useState<"form" | "yaml">("form");
  const [draft, setDraft] = useState<BriefDraft>(EMPTY_BRIEF);
  const [yaml, setYaml] = useState("");
  const [companies, setCompanies] = useState<Company[]>([]);
  const [companyId, setCompanyId] = useState<string>("none");
  const [start, setStart] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open) return;
    api.companies().then(setCompanies).catch(() => setCompanies([]));
    setCompanyId(activeCompany === null ? "none" : String(activeCompany));
    if (!yaml) api.briefTemplate().then((r) => setYaml(r.yaml)).catch(() => {});
  }, [open, activeCompany, yaml]);

  // Picking a company fills an empty brief with what's known about it.
  useEffect(() => {
    const c = companies.find((x) => String(x.id) === companyId);
    if (!c) return;
    setDraft((d) => ({
      ...d,
      product: d.product || c.name,
      url: d.url || c.website || "",
      description: d.description || c.description || "",
    }));
  }, [companyId, companies]);

  async function submit() {
    setSaving(true);
    try {
      const company_id = companyId === "none" ? null : Number(companyId);
      const body = mode === "yaml" ? { brief_yaml: yaml } : { brief: briefFromDraft(draft) };
      const { id } = await api.createTask({ ...body, company_id, start });
      toast.success(start ? t("Task created and started") : t("Task created"));
      setDraft(EMPTY_BRIEF);
      onCreated(id);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  const valid =
    mode === "yaml" ? yaml.trim().length > 0 : !!(draft.product.trim() && draft.description.trim() && draft.ideal_customer.trim());

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90dvh] overflow-y-auto sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>{t("New task")}</DialogTitle>
          <DialogDescription>
            {t("Describe the product and who buys it. The planner turns this into goals and searches the platforms you have keys for.")}
          </DialogDescription>
        </DialogHeader>
        <div className="flex flex-wrap items-end gap-4">
          <div className="flex min-w-56 flex-col gap-1.5">
            <Label>{t("Company")}</Label>
            <Select value={companyId} onValueChange={setCompanyId}>
              <SelectTrigger className="w-56">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="none">{t("No company")}</SelectItem>
                {companies.map((c) => (
                  <SelectItem key={c.id} value={String(c.id)}>
                    {c.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <Tabs value={mode} onValueChange={(v) => setMode(v as "form" | "yaml")} className="ml-auto">
            <TabsList>
              <TabsTrigger value="form">{t("Form")}</TabsTrigger>
              <TabsTrigger value="yaml">{t("YAML brief")}</TabsTrigger>
            </TabsList>
          </Tabs>
        </div>
        <Tabs value={mode}>
          <TabsContent value="form" className="mt-2">
            <BriefForm value={draft} onChange={setDraft} disabled={saving} />
          </TabsContent>
          <TabsContent value="yaml" className="mt-2">
            <Textarea
              value={yaml}
              onChange={(e) => setYaml(e.target.value)}
              rows={18}
              className="font-mono text-xs"
              spellCheck={false}
            />
          </TabsContent>
        </Tabs>
        <DialogFooter className="items-center sm:justify-between">
          <label className="flex items-center gap-2 text-sm">
            <Switch checked={start} onCheckedChange={setStart} />
            {t("Start right away")}
          </label>
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={saving}>
              {t("Cancel")}
            </Button>
            <Button onClick={submit} disabled={saving || !valid}>
              {saving ? t("Creating…") : t("Create task")}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function TasksPage() {
  const router = useRouter();
  const params = useSearchParams();
  const company = useActiveCompanyID();
  const { data, loading, reload } = usePoll(
    () => api.tasks({ company: company ?? undefined }),
    [company],
    4000,
  );
  const [q, setQ] = useState("");
  const [status, setStatus] = useState("all");
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(20);
  const [creating, setCreating] = useState(params.get("new") === "1");
  const [deleting, setDeleting] = useState<Task | null>(null);

  const rows = useMemo(() => {
    const ql = q.trim().toLowerCase();
    return (data ?? []).filter(
      (x) =>
        (status === "all" || x.status === status) &&
        (!ql || `${x.id} ${x.name} ${x.product ?? ""} ${x.company_name ?? ""}`.toLowerCase().includes(ql)),
    );
  }, [data, q, status]);
  const pageRows = rows.slice((page - 1) * pageSize, page * pageSize);

  const act = (p: Promise<unknown>, ok: string) =>
    p
      .then(() => {
        toast.success(ok);
        void reload();
      })
      .catch((e) => toast.error((e as Error).message));

  return (
    <div className="flex flex-1 flex-col gap-4 md:gap-6">
      <PageHeader title={t("Tasks")} description={t("Each task hunts for one product's buyers across the platforms")} />
      <Card className="gap-0 py-0">
        <CardContent className="px-0">
          <div className="flex flex-wrap items-center gap-2 px-4 py-4 lg:px-6">
            <InputGroup className="w-full sm:w-72">
              <InputGroupInput
                type="search"
                value={q}
                onChange={(e) => {
                  setQ(e.target.value);
                  setPage(1);
                }}
                placeholder={t("Search name / product / ID")}
              />
              <InputGroupAddon>
                <SearchIcon />
              </InputGroupAddon>
            </InputGroup>
            <Select
              value={status}
              onValueChange={(v) => {
                setStatus(v);
                setPage(1);
              }}
            >
              <SelectTrigger size="sm" className="w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{t("All statuses")}</SelectItem>
                {STATUSES.map((s) => (
                  <SelectItem key={s} value={s}>
                    {statusMeta("task", s).label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span className="text-muted-foreground text-xs">
              {t("{n}/{total} tasks", { n: rows.length, total: data?.length ?? 0 })}
            </span>
            <Button size="sm" className="ml-auto" onClick={() => setCreating(true)}>
              <Plus />
              {t("New task")}
            </Button>
          </div>
          {loading && !data ? (
            <Loading />
          ) : rows.length === 0 ? (
            <EmptyRow text={data?.length ? t("No task matches the filters.") : t("No tasks yet. Create one to start finding leads.")} />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-16 pl-4 lg:pl-6">{t("ID")}</TableHead>
                  <TableHead className="min-w-56">{t("Name")}</TableHead>
                  <TableHead>{t("Company")}</TableHead>
                  <TableHead>{t("Status")}</TableHead>
                  <TableHead>{t("Goal progress")}</TableHead>
                  <TableHead className="text-right">{t("Leads H/W/C")}</TableHead>
                  <TableHead className="text-right">{t("Intents")}</TableHead>
                  <TableHead className="text-right">{t("Tokens")}</TableHead>
                  <TableHead>{t("Created")}</TableHead>
                  <TableHead className="pr-4 text-right lg:pr-6">{t("Actions")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {pageRows.map((x) => {
                  const g = x.goals[0];
                  const running = x.status === "running";
                  const intents = Object.values(x.intents).reduce((a, b) => a + b, 0);
                  return (
                    <TableRow key={x.id}>
                      <TableCell className="pl-4 lg:pl-6">
                        <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">t-{x.id}</span>
                      </TableCell>
                      <TableCell>
                        <Link
                          prefetch={false}
                          href={`/function/tasks/detail?id=${x.id}`}
                          className="font-medium hover:underline"
                        >
                          {x.name}
                        </Link>
                        {x.end_reason && (
                          <div className="line-clamp-1 max-w-72 text-muted-foreground text-xs">{x.end_reason}</div>
                        )}
                      </TableCell>
                      <TableCell className="text-muted-foreground">{x.company_name ?? "—"}</TableCell>
                      <TableCell>
                        <StatusBadge domain="task" value={x.status} dot />
                      </TableCell>
                      <TableCell className="tabular-nums">
                        {g ? (
                          <span className={g.state === "met" ? "text-emerald-600 dark:text-emerald-400" : undefined}>
                            {g.have}/{g.target} {g.min_intent}+
                          </span>
                        ) : (
                          "—"
                        )}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        <span className="text-rose-600 dark:text-rose-400">{x.leads.hot}</span>/
                        <span className="text-amber-600 dark:text-amber-400">{x.leads.warm}</span>/
                        <span className="text-muted-foreground">{x.leads.cold}</span>
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {intents}
                        {x.intents.running > 0 && (
                          <span className="ml-1 text-blue-600 text-xs dark:text-blue-400">({x.intents.running} live)</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">{num(x.tokens)}</TableCell>
                      <TableCell className="text-muted-foreground text-xs tabular-nums">{fmtTime(x.created_at)}</TableCell>
                      <TableCell className="pr-4 lg:pr-6">
                        <div className="flex items-center justify-end gap-1">
                          <IconAction label={t("View")} onClick={() => router.push(`/function/tasks/detail?id=${x.id}`)}>
                            <Eye />
                          </IconAction>
                          {running ? (
                            <IconAction
                              label={x.running_here ? t("Pause") : t("Running in another process")}
                              disabled={!x.running_here}
                              onClick={() => act(api.pauseTask(x.id), t("Pausing — workers finish their current step"))}
                            >
                              <Pause />
                            </IconAction>
                          ) : (
                            <IconAction
                              label={x.status === "created" ? t("Start") : t("Resume")}
                              onClick={() => act(api.startTask(x.id), t("Task started"))}
                            >
                              <Play />
                            </IconAction>
                          )}
                          <IconAction label={t("Delete")} destructive disabled={running} onClick={() => setDeleting(x)}>
                            <Trash2 />
                          </IconAction>
                        </div>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
          <TablePagination
            page={page}
            pageSize={pageSize}
            total={rows.length}
            onPageChange={setPage}
            onPageSizeChange={(s) => {
              setPageSize(s);
              setPage(1);
            }}
          />
        </CardContent>
      </Card>

      <NewTaskDialog
        open={creating}
        onOpenChange={setCreating}
        onCreated={(id) => {
          setCreating(false);
          router.push(`/function/tasks/detail?id=${id}`);
        }}
      />
      <Confirm
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={t("Delete this task?")}
        description={t(
          "“{name}” and everything it found (leads, transcripts, records) will be deleted permanently. Communities stay in the shared source graph.",
          { name: deleting?.name ?? "" },
        )}
        onConfirm={() => deleting && act(api.deleteTask(deleting.id), t("Task deleted"))}
      />
    </div>
  );
}

export default function Page() {
  return (
    <Suspense fallback={<Loading />}>
      <TasksPage />
    </Suspense>
  );
}
