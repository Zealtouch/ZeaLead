"use client";

import { useEffect, useState } from "react";

import { useRouter } from "next/navigation";

import { ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogClose, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { t } from "@/i18n";
import { api } from "@/lib/api";
import { auth } from "@/lib/auth";

import { AuthShell } from "../_components/auth-shell";
import { ResponsibleUse } from "../_components/responsible-use";

const AGREED_KEY = "leadscout.responsible-use";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [checking, setChecking] = useState(true);
  const [agreed, setAgreed] = useState(false);
  const [termsOpen, setTermsOpen] = useState(false);

  useEffect(() => {
    if (auth.getToken()) {
      window.location.replace("/dashboard");
      return;
    }
    setAgreed(localStorage.getItem(AGREED_KEY) === "1");
    api
      .authStatus()
      .then(({ setup_required }) => {
        if (setup_required) router.replace("/setup");
      })
      .catch(() => setError(t("Unable to connect to the backend service")))
      .finally(() => setChecking(false));
  }, [router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!agreed) {
      setError(t("Please read and accept the responsible-use terms first"));
      return;
    }
    setLoading(true);
    setError("");
    try {
      const { token } = await api.login(username.trim(), password);
      localStorage.setItem(AGREED_KEY, "1");
      auth.setToken(token);
      window.location.replace("/dashboard");
    } catch (err) {
      setError((err as Error).message || t("Incorrect username or password"));
    } finally {
      setLoading(false);
    }
  }

  if (checking) {
    return (
      <div role="status" className="flex min-h-dvh items-center justify-center text-muted-foreground">
        {t("Checking login state…")}
      </div>
    );
  }

  return (
    <AuthShell title={t("Sign in")} subtitle={t("Welcome back — sign in to continue to leadscout")}>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div className="space-y-1.5">
          <Label htmlFor="username">{t("Username")}</Label>
          <Input
            id="username"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
            autoComplete="username"
          />
        </div>
        <div className="space-y-1.5">
          <Label htmlFor="password">{t("Password")}</Label>
          <Input
            id="password"
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder={t("Enter your password")}
            autoComplete="current-password"
          />
        </div>
        <div className="flex items-start gap-2">
          <Checkbox id="agree" checked={agreed} onCheckedChange={(v) => setAgreed(v === true)} className="mt-0.5" />
          <Label htmlFor="agree" className="text-sm font-normal leading-relaxed text-muted-foreground">
            {t("I have read and accept the")}
            <button
              type="button"
              onClick={() => setTermsOpen(true)}
              className="mx-1 font-medium text-primary underline-offset-4 hover:underline"
            >
              {t("responsible-use terms")}
            </button>
          </Label>
        </div>
        {error && <p className="text-sm text-destructive">{error}</p>}
        <Button type="submit" className="w-full" disabled={loading || !username || !password || !agreed}>
          {loading ? t("Signing in...") : t("Sign in")}
        </Button>
        <p className="text-center text-muted-foreground text-xs">
          {t("Forgot your password? Run")}{" "}
          <code className="rounded bg-muted px-1">./reset-password.sh &lt;username&gt;</code>
        </p>
      </form>

      <Dialog open={termsOpen} onOpenChange={setTermsOpen}>
        <DialogContent className="sm:max-w-xl">
          <DialogHeader className="flex-row items-center gap-3">
            <ShieldCheck className="size-5 text-primary" />
            <DialogTitle className="text-base">{t("Responsible use")}</DialogTitle>
          </DialogHeader>
          <ResponsibleUse />
          <DialogFooter>
            <DialogClose asChild>
              <Button variant="outline">{t("Close")}</Button>
            </DialogClose>
            <Button
              onClick={() => {
                setAgreed(true);
                setTermsOpen(false);
              }}
            >
              {t("I accept")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </AuthShell>
  );
}
