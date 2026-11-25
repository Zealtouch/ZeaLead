"use client";

import { useEffect, useState } from "react";

import { useRouter } from "next/navigation";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { t } from "@/i18n";
import { api } from "@/lib/api";
import { auth } from "@/lib/auth";

import { AuthShell } from "../_components/auth-shell";
import { ResponsibleUse } from "../_components/responsible-use";

const MIN = 10;

export default function SetupPage() {
  const router = useRouter();
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [agreed, setAgreed] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(true);

  useEffect(() => {
    api
      .authStatus()
      .then(({ setup_required }) => {
        if (!setup_required) router.replace("/login");
        else setChecking(false);
      })
      .catch(() => {
        setError(t("Unable to connect to the backend service"));
        setChecking(false);
      });
  }, [router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (password.length < MIN) return setError(t("Use at least {n} characters", { n: MIN }));
    if (password !== confirm) return setError(t("The two passwords do not match"));
    setLoading(true);
    setError("");
    try {
      const { token } = await api.setup(username.trim(), password);
      localStorage.setItem("zealead.responsible-use", "1");
      auth.setToken(token);
      window.location.replace("/dashboard");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  }

  if (checking) {
    return (
      <div role="status" className="flex min-h-dvh items-center justify-center text-muted-foreground">
        {t("Checking setup state…")}
      </div>
    );
  }

  return (
    <AuthShell
      title={t("Create the admin account")}
      subtitle={t("First run: this account manages users and system settings. You can add teammates later.")}
    >
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div className="space-y-1.5">
          <Label htmlFor="username">{t("Username")}</Label>
          <Input id="username" value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="password">{t("Password")}</Label>
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={t("At least {n} characters", { n: MIN })}
            autoFocus
            autoComplete="new-password"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="confirm">{t("Confirm password")}</Label>
          <Input
            id="confirm"
            type="password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoComplete="new-password"
          />
        </div>
        <details className="rounded-lg border p-3 text-sm">
          <summary className="cursor-pointer font-medium">{t("Responsible use")}</summary>
          <div className="mt-3">
            <ResponsibleUse />
          </div>
        </details>
        <div className="flex items-start gap-2">
          <Checkbox id="agree" checked={agreed} onCheckedChange={(v) => setAgreed(v === true)} className="mt-0.5" />
          <Label htmlFor="agree" className="text-sm font-normal leading-relaxed text-muted-foreground">
            {t("I have read and accept the responsible-use terms")}
          </Label>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button type="submit" className="w-full" disabled={loading || !username || !password || !agreed}>
          {loading ? t("Creating…") : t("Create account and continue")}
        </Button>
      </form>
    </AuthShell>
  );
}
