# Runbook: taking a business live on M-Pesa

1. **Prerequisites (the business):**
   - a Paybill, or a Till with its store number;
   - Lipa na M-Pesa Online (STK Push) enabled, with its **passkey** from Safaricom;
   - an account on the Daraja portal (developer.safaricom.co.ke) and a production app with the M-Pesa
     Express and C2B products.
2. **Try it first:** in Settings → Payments, connect the **sandbox**:
   - shortcode 174379 with the sandbox passkey and the app's sandbox keys;
   - send a prompt to Safaricom's test number 254708374149;
   - the sandbox does not reach a localhost callback, but the check job confirms prompts by STK Query.
3. **Go live:**
   - connect **Live** with the production keys; saving checks them with Safaricom;
   - click **Receive Paybill payments** to register the C2B URLs. Safaricom only accepts HTTPS URLs on a
     public domain, so this needs the production domain (ADR-0020).
4. **Lock down callbacks:** set `MPESA_CALLBACK_ALLOWED_IPS` to Safaricom's published callback IPs (ask
   Safaricom support for the current list), then restart the API.
5. **Check it works:**
   - pay a KES 1 invoice from the link with your own phone, and confirm the payment appears on the invoice
     with the M-Pesa receipt;
   - pay the Paybill by hand with a wrong account number, and confirm it shows in Payments → "M-Pesa
     payments to match".
6. **Troubleshooting:**
   - a prompt stuck as pending is checked every minute; after 5 minutes without an answer it is marked
     expired;
   - "M-Pesa rejected the consumer key or secret": the keys are for the wrong environment, or the app lacks
     the product;
   - wrong passkey: prompts fail with "Bad Request - Invalid Password"; reconnect with the right passkey.
