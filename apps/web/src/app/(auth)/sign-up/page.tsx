"use client";

import { zodResolver } from "@hookform/resolvers/zod";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Suspense, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { Field, FormError } from "@/components/forms/field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { authClient } from "@/lib/auth-client";
import { safeNext } from "@/lib/navigation";

const schema = z.object({
  name: z.string().trim().min(2, "Enter your name"),
  email: z.email("Enter a valid email address"),
  password: z.string().min(10, "Use at least 10 characters"),
});
type Values = z.infer<typeof schema>;

function SignUpForm() {
  const t = useTranslations("signUp");
  const common = useTranslations("common");
  const next = safeNext(useSearchParams().get("next"), "/onboarding");
  const [sentTo, setSentTo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const form = useForm<Values>({ resolver: zodResolver(schema) });

  async function onSubmit(values: Values) {
    setError(null);
    const callbackURL = `/verify-email?next=${encodeURIComponent(next)}`;
    const { error: failure } = await authClient.signUp.email({ ...values, callbackURL });
    if (failure) {
      setError(failure.code?.startsWith("USER_ALREADY_EXISTS") ? t("exists") : (failure.message ?? common("tryAgain")));
      return;
    }
    setSentTo(values.email);
  }

  if (sentTo) {
    return (
      <div role="status">
        <h1 className="mb-4 text-3xl">{t("checkInboxTitle")}</h1>
        <p className="text-lg">{t("checkInbox", { email: sentTo })}</p>
      </div>
    );
  }

  return (
    <>
      <h1 className="mb-6 text-3xl">{t("title")}</h1>
      <form onSubmit={form.handleSubmit(onSubmit)} className="grid gap-5" noValidate>
        <FormError message={error} />
        <Field label={common("name")} error={form.formState.errors.name?.message}>
          {(p) => <Input autoComplete="name" {...p} {...form.register("name")} />}
        </Field>
        <Field label={common("email")} error={form.formState.errors.email?.message}>
          {(p) => <Input type="email" autoComplete="email" inputMode="email" {...p} {...form.register("email")} />}
        </Field>
        <Field label={common("password")} hint={t("passwordHint")} error={form.formState.errors.password?.message}>
          {(p) => <Input type="password" autoComplete="new-password" {...p} {...form.register("password")} />}
        </Field>
        <Button type="submit" size="lg" disabled={form.formState.isSubmitting}>
          {t("submit")}
        </Button>
      </form>
      <p className="mt-6 text-sm">
        {t("haveAccount")}{" "}
        <Link href={`/sign-in?next=${encodeURIComponent(next)}`} className="font-bold text-primary underline-offset-4 hover:underline">
          {common("signIn")}
        </Link>
      </p>
    </>
  );
}

export default function SignUpPage() {
  return (
    <Suspense>
      <SignUpForm />
    </Suspense>
  );
}
