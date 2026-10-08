# mpesa

M-Pesa Daraja collection (Plan A1.3 R2.3, ADR-0015). Money goes from the client's phone straight to the
tenant's **own** Paybill or Till; we orchestrate and record.

- **Connection** (`PUT /mpesa/connection`, `org:update`):
  - environment `production`, `sandbox` or `simulator` (no network, every prompt is paid; refused in
    production);
  - Paybill or Till (store number plus till number);
  - Daraja consumer key and secret and passkey, checked with Safaricom (OAuth) before saving and stored
    encrypted (ADR-0018 keys);
  - a secret callback path is generated each time and also stored encrypted, to build the callback URLs;
  - `POST /mpesa/connection/register-c2b` registers the confirmation and validation URLs for Paybill
    payments made by hand.
- **Payment prompts (STK Push):**
  - from the app: `POST /invoices/{id}/mpesa-prompt` (`payment:write`);
  - from the client's link: `POST /public/links/{token}/pay` (scope `pay`, rate limited), polled through
    `GET …/pay/{attempt_id}`.
  - The amount is the balance rounded **up** to whole shillings; the excess becomes the client's credit.
- **Confirmation:**
  - callbacks are stored in `webhook_events` (unique per CheckoutRequestID or TransID), then a job acts on
    them;
  - a successful STK callback only counts after **STK Query** confirms it;
  - prompts whose callback is late are checked every minute (job) and when someone polls the status;
  - code 4999 means "still processing";
  - payments are recorded through `billing.record_payment` (method `mpesa`, reference = receipt) and are
    idempotent on the receipt.
- **Paybill payments (C2B):**
  - the account number is matched to an invoice's payment reference (case and spaces ignored);
  - anything else goes to the **unmatched** queue (`GET /mpesa/transactions?status=unmatched`), where the
    business assigns it to a client (credit or an invoice) or sets it aside with a reason;
  - owners, admins and accounts are notified.
- **Security:**
  - the callback path is secret per connection (sha256 lookup through a SECURITY DEFINER function);
  - optional IP allow-list `MPESA_CALLBACK_ALLOWED_IPS`;
  - validation accepts all payments, and matching happens on confirmation.
- **Tests:**
  - the simulator covers app and link prompts, stored and duplicated callbacks, cancelled prompts, C2B
    matching and the queue, and the IP allow-list;
  - `@pytest.mark.sandbox` calls the real Daraja sandbox when `DARAJA_SANDBOX_*` is set (local `.env`, CI
    secrets).
