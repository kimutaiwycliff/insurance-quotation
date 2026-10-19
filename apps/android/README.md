# Android app

Native Kotlin and Jetpack Compose (ADR-0026). It covers what agents do away from a desk; the web app remains
the full product.

## What it does
- **Sign in:** email and password, with two-factor codes; choose an agency if you belong to several.
- **Home:** today's numbers (tasks, renewals due, clients, policies, premiums to pass on, premium written).
  Tap a number to go to its list.
- **Clients:**
  - search by name or phone;
  - add and edit, with a warning when the phone, email, KRA PIN or ID matches someone you already have;
  - each client has tabs:
    - **Overview:** Call, WhatsApp, email and details;
    - **Timeline:** log calls, visits and WhatsApp chats;
    - **Tasks:** add, edit and tick off;
    - **Documents:** photograph IDs, KRA PINs and logbooks, or pick a file; photos are shrunk to save data;
      tap a document to open it.
- **Leads:**
  - pipeline counts per stage and the open pipeline value;
  - search;
  - add and edit;
  - Call and WhatsApp;
  - move between stages, with a reason when lost;
  - Won turns the lead into a client.
- **Tasks:** overdue, today, upcoming and done; add, edit and tick off.
- **More → Insurance** (when the plan includes it):
  - **Premium calculator:** pick a class and insurers, enter the sum insured; results come cheapest first,
    with levies and your commission. A banner shows while the Kenya levy pack awaits sign-off.
  - **Quotes:**
    - list by status; create from a client or from the list;
    - send by link, WhatsApp or email; see who accepted which option; open the PDF; withdraw;
    - create the policy from an accepted quote.
  - **Policies:**
    - list, search and status filters; add by hand or from a quote;
    - premium, paid and balance; record payments; activate once the insurer confirms;
    - WhatsApp and email reminders; renewal stage; quote the renewal.
  - **Renewals:** a board by stage (to contact, contacted, quoted, renewed, lost), with WhatsApp, contacted,
    lost (with reason), reopen, and quote renewal.
  - **Commission:** the year's expected, received and outstanding (after WHT), per insurer, WHT certificates,
    and record commission received from an insurer's statement.
- **More → Money:**
  - **Invoices:** what clients owe, overdue and collected this month; status filters.
    - **Editor:** lines from your saved items or typed in, quantity, discount and tax code.
    - **Draft and issue:** edit drafts, issue, send by link, WhatsApp or email, open the PDF.
    - **Getting paid:** record a payment, ask for an M-Pesa payment (followed live), or use the client's
      credit.
    - **Corrections:** credit notes, void, and KRA eTIMS details.
  - **Sales quotes:** headings and optional extras; send; Create invoice once accepted.
  - **Payments:** payments received, and M-Pesa payments to match (assign to a client and invoice, or set
    aside).
- **Client pages** also have Quotes, Policies and Billing tabs.
- **More → Agency:**
  - **Plan & billing:** status, trial, usage against limits; plans by month or year with founding prices;
    pay by M-Pesa prompt, followed live.
  - **Agency profile:** name, KRA PIN, licence and expiry, contacts; renewal and invoice reminder emails;
    eTIMS on or off.
  - **Team:** members and roles; invite colleagues, change roles, remove, cancel invitations (through the
    auth service, like the web).
  - **Help & guide:** the web's guide, searchable (same synonyms and M-Pesa spellings). Its links open the
    app's own screens where there is one.
- **Notifications:** a bell with an unread count on every screen. Tapping a notification opens the quote,
  invoice or client it is about.
- **More → On the web:** settings that need a big screen open in the browser: designs, insurers and
  products, items, numbering, M-Pesa setup, eTIMS settings, Excel import, two-factor.
- **More → Account:** switch agency, check for updates, sign out.

The help topics are generated from the web's (`apps/web/src/components/help/topics.ts`). After changing
those, run `python3 scripts/generate_help.py` (needs Node 22.6+).
- **Updates and remote config:** from `GET /api/v1/public/app-config`.
  - Versions below `ANDROID_MIN_VERSION_CODE` must update through Google Play before use.
  - Newer versions are offered as a background download.
  - `APP_NOTICE` shows a message to everyone; `APP_FEATURES` turns remote switches on.

## Run it against your local stack
1. `make up` in the repository root. Create an account and agency on http://localhost:3000.
2. Start an Android emulator (Android Studio → Device Manager).
3. In `apps/android`, run `./gradlew installDirectDebug`, or open the folder in Android Studio and press Run.
   - Debug builds talk to `http://10.0.2.2:3000` (site and sign-in) and `:8000` (API): the emulator's
     address for your computer.
   - On a real phone on the same Wi-Fi, use your computer's IP:
     `./gradlew installDirectDebug -PsiteUrl=http://192.168.1.20:3000 -PapiUrl=http://192.168.1.20:8000`.
     Also add that IP to `src/debug/res/xml/network_security_config.xml`.
4. Sign in with the account from step 1.

Requirements: JDK 17 or newer (`JAVA_HOME`) and the Android SDK (`ANDROID_HOME`, or `local.properties` with
`sdk.dir`). The Gradle wrapper downloads Gradle itself, checksum-pinned.

## Two builds
- **direct** (`assembleDirectDebug`, `assembleDirectRelease`): downloaded from our site; updates itself from
  `ANDROID_APK_URL` after checking its SHA-256. This is the one to install for now.
- **play** (`bundlePlayRelease`): for Google Play later; updates through Play.

## Checks
`make android-check` (lint, unit tests, debug build). CI also builds minified direct and play releases on every
PR.

## Layout
```
app/src/main/java/app/brokeros/android/
  core/     endpoints, JWT expiry, phone links, Keystore-encrypted session storage
  data/     auth (Better Auth via the web proxy), session state machine, API client (ETag, idempotency),
            feature calls and models (Crm.kt, Insurance.kt, Billing.kt, Account.kt)
  update/   app config (remote switches) and Google Play in-app updates
  ui/       theme, shared kit (components/), sign-in, home, clients, leads, tasks, insurance/, money/, account/ (more, plan, team, profile, notifications), help/
app/src/test/  unit tests (Ktor mock engine: no server needed)
```

## Releasing
See `docs/runbooks/android-release.md`.
