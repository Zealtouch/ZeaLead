"use client";

import { useState } from "react";

import { KeyRound, Plus, Trash2, UserRound } from "lucide-react";
import { toast } from "sonner";

import { Confirm } from "@/components/ls/confirm";
import { EmptyRow, Loading } from "@/components/ls/loading";
import { PageHeader } from "@/components/ls/page-header";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useCurrentUser } from "@/hooks/use-current-user";
import { usePoll } from "@/hooks/use-poll";
import { t } from "@/i18n";
import { api } from "@/lib/api";
import { ago, fmtDate } from "@/lib/format";
import type { User } from "@/lib/types";

const MIN_PW = 10;

function UserDialog({
  user,
  open,
  onOpenChange,
  onSaved,
}: {
  user: User | null; // null = create, else reset password
  open: boolean;
  onOpenChange: (o: boolean) => void;
  onSaved: () => void;
}) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("member");
  const [saving, setSaving] = useState(false);
  const [lastOpen, setLastOpen] = useState(false);
  if (open !== lastOpen) {
    setLastOpen(open);
    if (open) {
      setUsername("");
      setPassword("");
      setRole("member");
    }
  }

  async function save() {
    setSaving(true);
    try {
      if (user) await api.updateUser(user.id, { password });
      else await api.createUser(username.trim(), password, role);
      toast.success(user ? t("Password reset — {u} must sign in again", { u: user.username }) : t("User created"));
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
          <DialogTitle>{user ? t("Reset password for {u}", { u: user.username }) : t("New user")}</DialogTitle>
          <DialogDescription>
            {user
              ? t("Their existing sessions are signed out.")
              : t("Members can run tasks and work leads. Admins can also manage users and settings.")}
          </DialogDescription>
        </DialogHeader>
        <div className="grid gap-4">
          {!user && (
            <>
              <div className="grid gap-1.5">
                <Label htmlFor="u-name">{t("Username")}</Label>
                <Input id="u-name" value={username} autoComplete="off" onChange={(e) => setUsername(e.target.value)} />
              </div>
              <div className="grid gap-1.5">
                <Label>{t("Role")}</Label>
                <Select value={role} onValueChange={setRole}>
                  <SelectTrigger className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="member">{t("Member")}</SelectItem>
                    <SelectItem value="admin">{t("Admin")}</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </>
          )}
          <div className="grid gap-1.5">
            <Label htmlFor="u-pw">{user ? t("New password") : t("Password")}</Label>
            <Input
              id="u-pw"
              type="password"
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
            <p className="text-muted-foreground text-xs">{t("At least {n} characters.", { n: MIN_PW })}</p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("Cancel")}
          </Button>
          <Button onClick={save} disabled={saving || password.length < MIN_PW || (!user && !username.trim())}>
            {user ? t("Reset password") : t("Create user")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

export default function UsersPage() {
  const me = useCurrentUser();
  const { data, loading, error, reload } = usePoll(() => api.users(), []);
  const [dialog, setDialog] = useState(false);
  const [target, setTarget] = useState<User | null>(null);
  const [deleting, setDeleting] = useState<User | null>(null);

  async function setRole(u: User, role: string) {
    try {
      await api.updateUser(u.id, { role });
      toast.success(t("Role updated"));
      reload();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  async function remove(u: User) {
    try {
      await api.deleteUser(u.id);
      toast.success(t("User deleted"));
      reload();
    } catch (e) {
      toast.error((e as Error).message);
    }
  }

  return (
    <div className="flex flex-1 flex-col gap-4 md:gap-6">
      <PageHeader
        title={t("Users")}
        description={t("Who can sign in to this console")}
        actions={
          <Button
            size="sm"
            onClick={() => {
              setTarget(null);
              setDialog(true);
            }}
          >
            <Plus />
            {t("New user")}
          </Button>
        }
      />
      <Card className="gap-0 py-0">
        <CardContent className="px-0">
          {loading && !data ? (
            <Loading />
          ) : error && !data ? (
            <EmptyRow text={error} />
          ) : !data?.length ? (
            <EmptyRow text={t("No users.")} />
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="pl-4 lg:pl-6">{t("User")}</TableHead>
                  <TableHead>{t("Role")}</TableHead>
                  <TableHead>{t("Created")}</TableHead>
                  <TableHead>{t("Last sign-in")}</TableHead>
                  <TableHead className="pr-4 text-right lg:pr-6">{t("Actions")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {data.map((u) => {
                  const self = String(u.id) === me.id;
                  return (
                    <TableRow key={u.id}>
                      <TableCell className="pl-4 lg:pl-6">
                        <span className="flex items-center gap-2 font-medium">
                          <UserRound className="size-4 text-muted-foreground" />
                          {u.username}
                          {self && (
                            <Badge variant="secondary" className="text-[10px]">
                              {t("you")}
                            </Badge>
                          )}
                        </span>
                      </TableCell>
                      <TableCell>
                        <Select value={u.role} onValueChange={(v) => setRole(u, v)} disabled={self}>
                          <SelectTrigger size="sm" className="h-7 w-28">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="member">{t("Member")}</SelectItem>
                            <SelectItem value="admin">{t("Admin")}</SelectItem>
                          </SelectContent>
                        </Select>
                      </TableCell>
                      <TableCell className="text-muted-foreground text-xs">{fmtDate(u.created_at)}</TableCell>
                      <TableCell className="text-muted-foreground text-xs">{u.last_login_at ? ago(u.last_login_at) : t("never")}</TableCell>
                      <TableCell className="pr-4 text-right lg:pr-6">
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label={t("Reset password")}
                          onClick={() => {
                            setTarget(u);
                            setDialog(true);
                          }}
                        >
                          <KeyRound />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon-sm"
                          aria-label={t("Delete")}
                          disabled={self}
                          className="text-destructive hover:text-destructive"
                          onClick={() => setDeleting(u)}
                        >
                          <Trash2 />
                        </Button>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
      <UserDialog user={target} open={dialog} onOpenChange={setDialog} onSaved={reload} />
      <Confirm
        open={deleting !== null}
        onOpenChange={(o) => !o && setDeleting(null)}
        title={t("Delete user?")}
        description={t("{u} loses access immediately. Their tasks and leads stay.", { u: deleting?.username ?? "" })}
        onConfirm={() => deleting && remove(deleting)}
      />
    </div>
  );
}
