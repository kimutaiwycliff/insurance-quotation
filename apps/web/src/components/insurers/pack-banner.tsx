"use client";

import { useJurisdictionPackGet } from "@/lib/api/generated/insurers/insurers";

/** Shown wherever statutory amounts appear until the adviser signs the pack off (D4). */
export function PackBanner() {
  const pack = useJurisdictionPackGet();
  if (!pack.data || pack.data.signed) return null;
  return (
    <p role="note" className="rounded-md border border-maize bg-maize/10 px-3 py-2 text-sm">
      <strong>{pack.data.title} levies and stamp duty ({pack.data.version}) are awaiting adviser sign-off.</strong> Check
      totals against the insurer&apos;s quote before sending them to a client.
    </p>
  );
}
