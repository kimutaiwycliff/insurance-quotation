"use client";

import QRCode from "qrcode";
import { useTranslations } from "next-intl";
import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Field, FormError } from "@/components/forms/field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { authClient } from "@/lib/auth-client";

type Step = { kind: "idle" } | { kind: "password"; action: "on" | "off" } | { kind: "scan"; uri: string; qr: string; secret: string; backup: string[] };

export function SecurityPanel() {
  const t = useTranslations("security");
  const common = useTranslations("common");
  const session = authClient.useSession();
  const enabled = Boolean(session.data?.user.twoFactorEnabled);
  const [step, setStepState] = useState<Step>({ kind: "idle" });
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const setStep = (next: Step) => {
    setError(null);
    setStepState(next);
  };

  async function confirmPassword(event: FormEvent) {
    event.preventDefault();
    if (step.kind !== "password") return;
    setBusy(true);
    if (step.action === "off") {
      const { error: failure } = await authClient.twoFactor.disable({ password });
      setBusy(false);
      if (failure) return setError(failure.message ?? "Check your password and try again.");
      toast.success(t("turnedOff"));
      setStep({ kind: "idle" });
      await session.refetch();
      return;
    }
    const { data, error: failure } = await authClient.twoFactor.enable({ password });
    setBusy(false);
    if (failure || !data || !("totpURI" in data)) {
      return setError(failure?.message ?? "Check your password and try again.");
    }
    const secret = new URL(data.totpURI).searchParams.get("secret") ?? "";
    // Rendered locally: the secret never goes to a third-party QR service.
    const qr = await QRCode.toDataURL(data.totpURI, { margin: 1, width: 220 });
    setStep({ kind: "scan", uri: data.totpURI, qr, secret, backup: data.backupCodes });
    setPassword("");
  }

  async function verify(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    const { error: failure } = await authClient.twoFactor.verifyTotp({ code: code.replace(/\s/g, "") });
    setBusy(false);
    if (failure) return setError("That code is not valid. Enter the current code from the app.");
    toast.success(t("turnedOn"));
    setStep({ kind: "idle" });
    setCode("");
    await session.refetch();
  }

  return (
    <section aria-labelledby="tfa" className="grid max-w-xl gap-5">
      <div className="flex items-center gap-3">
        <h3 id="tfa" className="text-xl">{t("twoFactorTitle")}</h3>
        <Badge variant={enabled ? "default" : "secondary"}>{enabled ? t("enabled") : t("disabled")}</Badge>
      </div>
      <p className="text-muted-foreground">{t("twoFactorBody")}</p>
      <FormError message={error} />

      {step.kind === "idle" && (
        <div>
          <Button variant={enabled ? "outline" : "default"} onClick={() => setStep({ kind: "password", action: enabled ? "off" : "on" })}>
            {enabled ? t("turnOff") : t("turnOn")}
          </Button>
        </div>
      )}

      {step.kind === "password" && (
        <form onSubmit={confirmPassword} className="grid gap-4">
          <Field label={t("confirmPassword")}>
            {(p) => <Input {...p} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} autoFocus />}
          </Field>
          <div className="flex gap-2">
            <Button type="submit" disabled={busy || !password}>{common("continue")}</Button>
            <Button type="button" variant="ghost" onClick={() => setStep({ kind: "idle" })}>{common("cancel")}</Button>
          </div>
        </form>
      )}

      {step.kind === "scan" && (
        <form onSubmit={verify} className="grid gap-5">
          <p>{t("scan")}</p>
          {/* eslint-disable-next-line @next/next/no-img-element -- data URL generated in the browser */}
          <img src={step.qr} width={220} height={220} alt="QR code for your authenticator app" className="rounded-md border bg-white p-2" />
          <p className="text-sm">
            {t("manual")} <code className="tabular rounded bg-muted px-1.5 py-0.5 break-all">{step.secret}</code>
          </p>
          <div className="rounded-md border border-maize bg-maize/10 p-3">
            <p className="mb-2 text-sm font-bold">{t("backupCodes")}</p>
            <ul className="tabular grid grid-cols-2 gap-1 text-sm">
              {step.backup.map((c) => <li key={c}>{c}</li>)}
            </ul>
          </div>
          <Field label="6-digit code">
            {(p) => <Input {...p} inputMode="numeric" autoComplete="one-time-code" value={code} onChange={(e) => setCode(e.target.value)} className="tabular w-40 text-lg tracking-widest" />}
          </Field>
          <div>
            <Button type="submit" disabled={busy || code.replace(/\s/g, "").length < 6}>{t("verify")}</Button>
          </div>
        </form>
      )}
    </section>
  );
}
