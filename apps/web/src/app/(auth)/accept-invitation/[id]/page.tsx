"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { FormError } from "@/components/forms/field";
import { Button } from "@/components/ui/button";
import { authClient, bumpOrgEpoch } from "@/lib/auth-client";

export default function AcceptInvitationPage() {
  const t = useTranslations("invitation");
  const common = useTranslations("common");
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const session = authClient.useSession();
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const here = `/accept-invitation/${id}`;

  async function accept() {
    setBusy(true);
    const { data, error: failure } = await authClient.organization.acceptInvitation({ invitationId: id });
    if (failure || !data) {
      setBusy(false);
      setError(t("failed"));
      return;
    }
    await authClient.organization.setActive({ organizationId: data.invitation.organizationId });
    bumpOrgEpoch();
    router.replace("/");
    router.refresh();
  }

  return (
    <>
      <h1 className="mb-4 text-3xl">{t("title")}</h1>
      <FormError message={error} />
      {session.isPending ? null : session.data ? (
        <Button size="lg" onClick={accept} disabled={busy} className="mt-4">
          {t("accept")}
        </Button>
      ) : (
        <>
          <p className="mb-6 text-lg">{t("signedOut")}</p>
          <div className="flex flex-wrap gap-3">
            <Button asChild size="lg"><Link href={`/sign-in?next=${encodeURIComponent(here)}`}>{common("signIn")}</Link></Button>
            <Button asChild size="lg" variant="outline"><Link href={`/sign-up?next=${encodeURIComponent(here)}`}>Create an account</Link></Button>
          </div>
        </>
      )}
    </>
  );
}
