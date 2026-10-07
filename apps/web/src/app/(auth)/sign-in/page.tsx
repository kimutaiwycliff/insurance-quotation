"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Suspense, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Field, FormError } from "@/components/forms/field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { authClient } from "@/lib/auth-client";
import { safeNext } from "@/lib/navigation";

const schema = z.object({ email: z.email(), password: z.string().min(1) });
type Values = z.infer<typeof schema>;

function SignInForm() {
  const t = useTranslations("signIn");
  const common = useTranslations("common");
  const router = useRouter();
  const next = safeNext(useSearchParams().get("next"));
  const [error, setError] = useState<string | null>(null);
  const [unverified, setUnverified] = useState<string | null>(null);
  const [resent, setResent] = useState(false);
  const form = useForm<Values>({ resolver: zodResolver(schema) });

  async function onSubmit(values: Values) {
    setError(null);
    setUnverified(null);
    const { error: failure } = await authClient.signIn.email({ ...values, callbackURL: next });
    if (!failure) {
      router.replace(next);
      router.refresh();
      return;
    }
    if (failure.code === "EMAIL_NOT_VERIFIED") setUnverified(values.email);
    else setError(t("invalid"));
  }

  async function resend() {
    if (!unverified) return;
    await authClient.sendVerificationEmail({ email: unverified, callbackURL: "/verify-email" });
    setResent(true);
  }

  return (
    <>
      <h1 className="mb-6 text-3xl">{t("title")}</h1>
      <form onSubmit={form.handleSubmit(onSubmit)} className="grid gap-5" noValidate>
        <FormError message={error} />
        {unverified && (
          <div role="status" className="rounded-md border border-maize bg-maize/10 px-3 py-2 text-sm">
            <p>{t("unverified", { email: unverified })}</p>
            {resent ? (
              <p className="mt-1 font-bold">{t("resent")}</p>
            ) : (
              <button type="button" onClick={resend} className="mt-1 font-bold text-primary underline">
                {t("resend")}
              </button>
            )}
          </div>
        )}
        <Field label={common("email")} error={form.formState.errors.email?.message}>
          {(p) => <Input type="email" autoComplete="email" inputMode="email" {...p} {...form.register("email")} />}
        </Field>
        <Field label={common("password")} error={form.formState.errors.password?.message}>
          {(p) => <Input type="password" autoComplete="current-password" {...p} {...form.register("password")} />}
        </Field>
        <Button type="submit" size="lg" disabled={form.formState.isSubmitting}>
          {t("submit")}
        </Button>
      </form>
      <div className="mt-6 grid gap-2 text-sm">
        <Link href="/forgot-password" className="text-primary underline-offset-4 hover:underline">
          {t("forgot")}
        </Link>
        <p>
          {t("noAccount")}{" "}
          <Link href={`/sign-up?next=${encodeURIComponent(next)}`} className="font-bold text-primary underline-offset-4 hover:underline">
            {t("createAccount")}
          </Link>
        </p>
      </div>
    </>
  );
}

export default function SignInPage() {
  return (
    <Suspense>
      <SignInForm />
    </Suspense>
  );
}
