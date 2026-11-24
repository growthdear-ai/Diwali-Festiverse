"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";
import { Logo } from "@/components/common";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Field, Input } from "@/components/ui/field";
import { useAuth } from "@/lib/auth";

const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

/** Only allow same-origin relative redirects. */
function safeNext(next: string | null) {
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard";
}

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const { login, register, status } = useAuth();
  const router = useRouter();
  const params = useSearchParams();
  const next = safeNext(params.get("next"));
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [formError, setFormError] = useState<string | null>(params.get("expired") ? "Your session expired. Please log in again." : null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (status === "authenticated") router.replace(next);
  }, [status, next, router]);

  function validate() {
    const e: Record<string, string> = {};
    if (mode === "register" && (name.trim().length < 2 || name.trim().length > 120)) e.name = "Enter your name (2–120 characters).";
    if (!EMAIL_RE.test(email.trim())) e.email = "Enter a valid email address.";
    if (mode === "register" ? password.length < 8 || password.length > 128 : !password) e.password = mode === "register" ? "Use at least 8 characters." : "Enter your password.";
    setErrors(e);
    return !Object.keys(e).length;
  }

  async function submit(ev: React.FormEvent) {
    ev.preventDefault();
    if (!validate()) return;
    setBusy(true);
    setFormError(null);
    try {
      if (mode === "login") await login(email.trim(), password);
      else await register(name.trim(), email.trim(), password);
      router.replace(next);
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Something went wrong");
    } finally {
      setBusy(false);
    }
  }

  const other = mode === "login" ? "/register" : "/login";
  const otherHref = params.get("next") ? `${other}?next=${encodeURIComponent(next)}` : other;

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center px-4 py-10">
      <Logo className="mb-8" />
      <Card className="w-full max-w-sm p-6 sm:p-7">
        <h1 className="text-xl font-semibold tracking-tight">{mode === "login" ? "Welcome back" : "Create your account"}</h1>
        <p className="mt-1 text-sm text-muted-foreground">{mode === "login" ? "Log in to see what Nazar spotted." : "Takes a minute. Then invite your family."}</p>
        <form onSubmit={submit} noValidate className="mt-6 space-y-4">
          {mode === "register" && (
            <Field label="Name" htmlFor="name" error={errors.name}>
              <Input id="name" autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} aria-invalid={Boolean(errors.name)} aria-describedby={errors.name ? "name-error" : undefined} />
            </Field>
          )}
          <Field label="Email" htmlFor="email" error={errors.email}>
            <Input id="email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} aria-invalid={Boolean(errors.email)} aria-describedby={errors.email ? "email-error" : undefined} />
          </Field>
          <Field label="Password" htmlFor="password" error={errors.password} hint={mode === "register" ? "At least 8 characters." : undefined}>
            <Input
              id="password"
              type="password"
              autoComplete={mode === "login" ? "current-password" : "new-password"}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-invalid={Boolean(errors.password)}
              aria-describedby={errors.password ? "password-error" : undefined}
            />
          </Field>
          {formError && (
            <p className="rounded-[10px] border border-danger/25 bg-danger/5 px-3 py-2 text-[13px] text-danger" role="alert">
              {formError}
            </p>
          )}
          <Button type="submit" className="w-full" loading={busy}>
            {mode === "login" ? "Log in" : "Create account"}
          </Button>
        </form>
      </Card>
      <p className="mt-6 text-sm text-muted-foreground">
        {mode === "login" ? "New to Nazar Rakho?" : "Already have an account?"}{" "}
        <Link href={otherHref} className="font-medium text-primary hover:underline">
          {mode === "login" ? "Create an account" : "Log in"}
        </Link>
      </p>
    </div>
  );
}
