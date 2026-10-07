"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Suspense, useState, type FormEvent } from "react";

import { Field, FormError } from "@/components/forms/field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { authClient } from "@/lib/auth-client";

function ResetForm() {
  const t = useTranslations("reset");
  const common = useTranslations("common");
  const params = useSearchParams();
  const token = params.get("token");
  const [password, setPassword] = useState("");
  const [state, setState] = useState<"idle" | "done" | "invalid">(token && !params.get("error") ? "idle" : "invalid");

  async function submit(event: FormEvent) {
    event.preventDefault();
    const { error } = await authClient.resetPassword({ newPassword: password, token: token ?? "" });
    setState(error ? "invalid" : "done");
  }

  return (
    <>
      <h1 className="mb-6 text-3xl">{t("title")}</h1>
      {state === "done" && (
        <p role="status" className="text-lg">
          {t("done")}{" "}
          <Link href="/sign-in" className="font-bold text-primary underline">{common("signIn")}</Link>
        </p>
      )}
      {state === "invalid" && (
        <FormError message={t("invalid")} />
      )}
      {state === "idle" && (
        <form onSubmit={submit} className="grid gap-5">
          <Field label={common("password")} hint="At least 10 characters.">
            {(p) => <Input {...p} type="password" autoComplete="new-password" minLength={10} required value={password} onChange={(e) => setPassword(e.target.value)} />}
          </Field>
          <Button type="submit" size="lg" disabled={password.length < 10}>{t("submit")}</Button>
        </form>
      )}
    </>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense>
      <ResetForm />
    </Suspense>
  );
}
