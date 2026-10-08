# policies

The agent's **policy book** and **renewals** (Plan A1.1 R1.4, ADR-0019).

- **Policy:** client, insurer and product (snapshots), class, insurer's policy number, what is covered
  (`description` and `details`), cover dates, total premium (levies included), breakdown and expected commission
  (from the quote; internal only), and `collection_mode`.
- **Sources:**
  - `POST /policies/from-quote` uses the option the client accepted. If the client accepted by phone, the agent
    gives `option`, the quote is marked accepted and its link revoked.
  - `POST /policies` takes an existing policy entered by hand (with `renewed_from_id` for a renewal written
    elsewhere).
- **No premium, no cover:**
  - a policy is `pending` until `POST /policies/{id}/activate` with `insurer_confirmed: true`;
  - activation then needs full payment, or an exception from the pack's `premium_exceptions` (Regs r.43).
- **Payments:**
  - recorded (never held): `POST /policies/{id}/payments`, then `/void` or `/remitted` per payment;
  - an agent-collected payment opens a same-day "remit" task (Regs r.42);
  - these endpoints need `premium:write` (agents, accounts, owners).
- **Renewals:**
  - `GET /renewals` lists active policies ending within the window (and up to 30 days past), by stage:
    `due → contacted → quoted → renewed | lost`;
  - `POST /policies/{id}/remind` logs a contact on the client timeline (email sends the `policy.renewal_due`
    template; WhatsApp returns a click-to-chat link);
  - `POST /policies/{id}/renewal-quote` starts a quote for the same client and details;
  - converting that quote (or entering a renewal by hand) links the new policy and marks the old one as
    renewed.
- **Reminder job** (`policies.enqueue_renewal_reminders`, daily at 08:00 Nairobi):
  - scans tenants through the definer function `app.policies_due_for_renewal_reminder()`;
  - for each policy, takes the smallest of the agency's `renewal_reminder_days` that has been reached;
  - reminds once per `(policy, offset)` (`renewal_reminders` table): a notification to the owner, plus an
    email to the client if `renewal_client_emails` is on (off by default; reminders stream, with unsubscribe).
- **Scoping:** as clients (`client:read:own|all`, by `owner_user_id`). Policies are cancelled, never deleted.
