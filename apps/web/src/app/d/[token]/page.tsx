import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { Seal } from "@/components/brand/seal";
import { PublicActions } from "@/components/public/public-actions";
import type { PublicLinkView } from "@/lib/api/generated/model";
import { serverEnv } from "@/lib/server/env";

export const metadata: Metadata = { title: "Your document", robots: { index: false, follow: false } };

async function load(token: string): Promise<{ view: PublicLinkView } | { gone: true } | null> {
  if (!/^[A-Za-z0-9_-]{43}$/.test(token)) return null;
  const response = await fetch(`${serverEnv.apiUrl}/api/v1/public/links/${token}`, { cache: "no-store" });
  if (response.status === 410) return { gone: true };
  if (!response.ok) return null;
  return { view: (await response.json()) as PublicLinkView };
}

/** The page a client opens from an agent's message: light, mostly server-rendered, works on slow phones. */
export default async function PublicDocumentPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const result = await load(token);
  if (!result) notFound();
  if ("gone" in result) {
    return (
      <main className="mx-auto grid min-h-dvh max-w-xl content-center gap-3 px-5 text-center">
        <h1 className="text-2xl">This link is no longer available</h1>
        <p className="text-muted-foreground">It has expired or was withdrawn. Ask your agent for a new one.</p>
      </main>
    );
  }
  const { view } = result;
  return (
    <main className="mx-auto grid max-w-4xl gap-5 px-4 py-6 sm:py-10">
      <header className="flex items-center gap-3">
        <Seal name={view.tenant.name} size={44} className="text-primary" />
        <div>
          <p className="font-heading text-lg font-bold">{view.tenant.name}</p>
          <h1 className="text-2xl">{view.title}</h1>
        </div>
      </header>
      <PublicActions token={token} view={view} />
      {view.has_web_view && (
        <iframe
          title={view.title}
          src={`/public-api/links/${token}/html`}
          sandbox=""
          loading="lazy"
          className="h-[75vh] w-full rounded-lg border bg-white"
        />
      )}
    </main>
  );
}
