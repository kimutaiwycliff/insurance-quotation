import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { Button } from "@/components/ui/button";
import { safeNext } from "@/lib/navigation";

/** Better Auth redirects here after the confirmation link (with ?error=... if it failed). */
export default async function VerifyEmailPage({
  searchParams,
}: {
  searchParams: Promise<{ error?: string; next?: string }>;
}) {
  const t = await getTranslations("verify");
  const params = await searchParams;
  if (params.error) {
    return (
      <>
        <h1 className="mb-4 text-3xl">{t("failedTitle")}</h1>
        <p className="mb-6 text-lg">{t("failed")}</p>
        <Button asChild size="lg"><Link href="/sign-in">Sign in</Link></Button>
      </>
    );
  }
  return (
    <>
      <h1 className="mb-4 text-3xl">{t("title")}</h1>
      <p className="mb-6 text-lg">{t("body")}</p>
      <Button asChild size="lg"><Link href={safeNext(params.next, "/onboarding")}>{t("next")}</Link></Button>
    </>
  );
}
