import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import type { ReactElement } from "react";

import messages from "../../messages/en.json";
import { MeProvider } from "@/components/shell/me-context";
import type { Me } from "@/lib/me";

export const OWNER: Me = {
  user_id: "usr_1",
  email: "wanjiku@example.com",
  name: "Wanjiku Kamau",
  tenant: { id: "00000000-0000-0000-0000-000000000001", name: "Wanjiku Insurance Agency", slug: "wanjiku" },
  role: "owner",
  permissions: ["org:read", "org:update", "numbering:read", "numbering:manage", "member:read", "branding:manage"] as Me["permissions"],
  mfa_enrolled: false,
  mfa_required: false,
  plan: "agency",
  features: ["insurance", "comparison_quotes", "commission", "book_import", "client_reminders", "branding", "etims", "team"],
  read_only: false,
};

export function renderWithProviders(ui: ReactElement, { me = OWNER }: { me?: Me } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <NextIntlClientProvider locale="en" messages={messages} timeZone="Africa/Nairobi">
      <QueryClientProvider client={client}>
        <MeProvider me={me}>{ui}</MeProvider>
      </QueryClientProvider>
    </NextIntlClientProvider>,
  );
}
