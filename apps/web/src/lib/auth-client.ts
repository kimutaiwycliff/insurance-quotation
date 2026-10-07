"use client";

import { organizationClient, twoFactorClient } from "better-auth/client/plugins";
import { createAuthClient } from "better-auth/react";

import { ac, roles } from "@/lib/roles";
import { randomId } from "@/lib/utils";


/** Talks to the auth service through the same-origin /api/auth proxy (cookies stay first-party). */
export const authClient = createAuthClient({
  plugins: [
    organizationClient({ ac, roles }),
    twoFactorClient({
      onTwoFactorRedirect() {
        // Runs inside the auth client, outside React: a full navigation is intended here.
        // eslint-disable-next-line @next/next/no-location-assign-relative-destination
        window.location.href = "/two-factor";
      },
    }),
  ],
});

/** After creating or switching an organization: bust the server's API-token cache for this browser. */
export function bumpOrgEpoch(): void {
  document.cookie = `org_epoch=${randomId()}; path=/; samesite=lax`;
}
