# quotes

Insurance quotes: a client, a risk and 1–8 insurer options. Each option freezes the calculator output (breakdown,
pack version, legal sources). Commission is stored on the option for the agent and never serialised into
anything a client sees.

- **Lifecycle:** draft (re-price with `PUT /quotes/{id}/options`) → sent → accepted | declined (by the client) |
  withdrawn. A sent quote past `valid_until` reads as `expired` and cannot be accepted.
- **Send** (`POST /quotes/{id}/send`) does four things:
  - allocates the number;
  - renders the branded comparison PDF;
  - creates a link (view and accept), emailed if there is an address;
  - returns the URL and a WhatsApp share URL.
  Linked open leads move to "quoted".
- **Public:** the link target `quote` serves HTML, PDF, choices and state. `POST /public/links/{token}/accept`
  takes `{option, name, phone?, email?, agree_terms: true}`, and `.../decline` takes `{reason}`. Evidence
  (hashed IP, user agent, timestamp) is stored on the quote, and the owner is notified (`quote.answered`).
- **D5:** `tenants.multi_insurer_quotes` (organization setting) limits quotes to one insurer when off.
- **Scoping:** as clients (`client:read:own|all`); writes need `client:write`.
