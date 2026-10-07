"use client";

import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";

import { Field, FormError } from "@/components/forms/field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { authClient } from "@/lib/auth-client";

export default function TwoFactorPage() {
  const t = useTranslations("twoFactor");
  const router = useRouter();
  const [backup, setBackup] = useState(false);
  const [code, setCode] = useState("");
  const [trust, setTrust] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const { error: failure } = backup
      ? await authClient.twoFactor.verifyBackupCode({ code: code.trim(), trustDevice: trust })
      : await authClient.twoFactor.verifyTotp({ code: code.replace(/\s/g, ""), trustDevice: trust });
    setBusy(false);
    if (failure) {
      setError(t("invalid"));
      return;
    }
    router.replace("/");
    router.refresh();
  }

  return (
    <>
      <h1 className="mb-2 text-3xl">{t("title")}</h1>
      <p className="mb-6 text-muted-foreground">{t("body")}</p>
      <form onSubmit={submit} className="grid gap-5">
        <FormError message={error} />
        <Field label={backup ? t("backupCode") : t("code")}>
          {(p) => (
            <Input
              {...p}
              value={code}
              onChange={(e) => setCode(e.target.value)}
              autoComplete="one-time-code"
              inputMode={backup ? "text" : "numeric"}
              className="tabular text-lg tracking-widest"
              autoFocus
            />
          )}
        </Field>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" checked={trust} onChange={(e) => setTrust(e.target.checked)} className="size-4 accent-[var(--acacia)]" />
          {t("trust")}
        </label>
        <Button type="submit" size="lg" disabled={busy || code.length < 6}>
          {t("submit")}
        </Button>
      </form>
      <button type="button" onClick={() => setBackup(!backup)} className="mt-6 text-sm text-primary underline-offset-4 hover:underline">
        {backup ? t("useApp") : t("useBackup")}
      </button>
    </>
  );
}
