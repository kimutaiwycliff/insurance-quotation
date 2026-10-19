import { Download, ShieldCheck, Smartphone } from "lucide-react";
import Link from "next/link";

import { serverEnv } from "@/lib/server/env";

export const metadata = { title: "Get the Android app" };
export const dynamic = "force-dynamic";

interface AppConfig {
  android: { latest_version_code: number; apk_url: string; apk_sha256: string; store_url: string };
}

async function appConfig(): Promise<AppConfig | null> {
  try {
    const response = await fetch(`${serverEnv.apiUrl}/api/v1/public/app-config`, { cache: "no-store" });
    return response.ok ? ((await response.json()) as AppConfig) : null;
  } catch {
    return null;
  }
}

/** The version from a file name like brokeros-0.3.0.apk. */
function versionOf(url: string): string | null {
  return /-(\d+\.\d+\.\d+)\.apk$/.exec(url)?.[1] ?? null;
}

/** Public: where agents download the Android app (no Play Store yet; ADR-0026 amendment). */
export default async function DownloadPage() {
  const config = await appConfig();
  const android = config?.android;
  const apk = android?.apk_url || "";
  const version = versionOf(apk);
  return (
    <div className="grid gap-6">
      <div className="grid gap-2">
        <h1 className="text-3xl">Get the Android app</h1>
        <p className="text-muted-foreground">
          Clients, quotes, renewals, invoices and M-Pesa in your pocket. Sign in with the same email you use on the web.
        </p>
      </div>
      {android?.store_url ? (
        <a href={android.store_url} className="inline-flex h-12 items-center justify-center gap-2 rounded-md bg-primary px-5 font-bold text-primary-foreground">
          <Smartphone aria-hidden="true" className="size-5" /> Get it on Google Play
        </a>
      ) : apk ? (
        <a href={apk} download className="inline-flex h-12 items-center justify-center gap-2 rounded-md bg-primary px-5 font-bold text-primary-foreground">
          <Download aria-hidden="true" className="size-5" /> Download for Android{version ? ` (version ${version})` : ""}
        </a>
      ) : (
        <p role="status" className="rounded-md border border-dashed p-4">
          The Android app is coming soon. Meanwhile the web app works well on your phone&apos;s browser.
        </p>
      )}
      {apk && !android?.store_url && (
        <section aria-labelledby="install-heading" className="grid gap-3">
          <h2 id="install-heading" className="text-xl">Installing it</h2>
          <ol className="grid list-decimal gap-2 pl-5">
            <li>Tap <strong>Download for Android</strong> on your phone.</li>
            <li>Open the downloaded file. Android asks to allow installs from your browser: tap <strong>Settings</strong>, turn it on, then go back.</li>
            <li>Tap <strong>Install</strong>, open the app and sign in.</li>
          </ol>
          <p className="text-sm text-muted-foreground">
            Updates arrive inside the app: it tells you when a new version is ready. Needs Android 8 or newer.
          </p>
          {android?.apk_sha256 && (
            <p className="flex gap-2 text-sm text-muted-foreground">
              <ShieldCheck aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
              <span>
                The app is signed by us, and every update is checked before it installs. File fingerprint (SHA-256):{" "}
                <code className="break-all">{android.apk_sha256}</code>
              </span>
            </p>
          )}
        </section>
      )}
      <p className="text-sm">
        <Link href="/sign-in" className="text-primary underline-offset-4 hover:underline">Back to sign in</Link>
      </p>
    </div>
  );
}
