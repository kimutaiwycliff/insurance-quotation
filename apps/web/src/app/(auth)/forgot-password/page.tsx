"use client";

import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { Field } from "@/components/forms/field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { authClient } from "@/lib/auth-client";

export default function ForgotPasswordPage() {
  const t = useTranslations("forgot");
  const common = useTranslations("common");
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    await authClient.requestPasswordReset({ email, redirectTo: "/reset-password" });
    setSent(true); // same answer whether or not the account exists
  }

  return (
    <>
      <h1 className="mb-2 text-3xl">{t("title")}</h1>
      {sent ? (
        <p role="status" className="text-lg">{t("sent", { email })}</p>
      ) : (
        <>
          <p className="mb-6 text-muted-foreground">{t("body")}</p>
          <form onSubmit={submit} className="grid gap-5">
            <Field label={common("email")}>
              {(p) => <Input {...p} type="email" autoComplete="email" required value={email} onChange={(e) => setEmail(e.target.value)} />}
            </Field>
            <Button type="submit" size="lg">{t("submit")}</Button>
          </form>
        </>
      )}
    </>
  );
}
