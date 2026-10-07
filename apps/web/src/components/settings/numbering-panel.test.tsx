import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { NumberingPanel } from "@/components/settings/numbering-panel";
import { server } from "@/test/msw";
import { OWNER, renderWithProviders } from "@/test/render";

const scheme = {
  id: "s1",
  document_type: "invoice",
  branch_id: null,
  pattern: "INV-{YYYY}-{SEQ:5}",
  reset_period: "yearly",
  start_at: 1,
  is_active: true,
  version: 3,
};

describe("NumberingPanel", () => {
  it("previews a new format and saves it with If-Match", async () => {
    let ifMatch: string | null = null;
    let saved: unknown = null;
    server.use(
      http.get("*/bff/api/v1/numbering-schemes", () => HttpResponse.json([scheme])),
      http.post("*/bff/api/v1/numbering-schemes/preview", async ({ request }) => {
        const body = (await request.json()) as { pattern: string };
        if (!body.pattern.includes("{SEQ")) {
          return HttpResponse.json(
            { status: 422, code: "validation_error", title: "x", errors: [{ field: "body.pattern", message: "Pattern must contain {SEQ} exactly once", code: "value_error" }] },
            { status: 422 },
          );
        }
        return HttpResponse.json({ examples: [body.pattern.replace("{SEQ:5}", "00001"), "…", "…"] });
      }),
      http.patch("*/bff/api/v1/numbering-schemes/s1", async ({ request }) => {
        ifMatch = request.headers.get("If-Match");
        saved = await request.json();
        return HttpResponse.json({ ...scheme, pattern: "FA/{SEQ:5}", version: 4 });
      }),
    );
    renderWithProviders(<NumberingPanel />);

    const input = await screen.findByLabelText("Format");
    await waitFor(() => expect(screen.getByText(/INV-\{YYYY\}-00001/)).toBeInTheDocument());

    await userEvent.clear(input);
    await userEvent.type(input, "FA/");
    expect(await screen.findByText(/exactly once/)).toBeInTheDocument();

    await userEvent.type(input, "{{SEQ:5}");
    await waitFor(() => expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled());
    await userEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(saved).toEqual({ pattern: "FA/{SEQ:5}", reset_period: "yearly" }));
    expect(ifMatch).toBe('W/"3"');
  });

  it("is read-only without numbering:manage", async () => {
    server.use(
      http.get("*/bff/api/v1/numbering-schemes", () => HttpResponse.json([scheme])),
      http.post("*/bff/api/v1/numbering-schemes/preview", () => HttpResponse.json({ examples: ["INV-2026-00001"] })),
    );
    renderWithProviders(<NumberingPanel />, { me: { ...OWNER, role: "agent", permissions: ["numbering:read"] as never } });
    expect(await screen.findByLabelText("Format")).toBeDisabled();
  });
});
