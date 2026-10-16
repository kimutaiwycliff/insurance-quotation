/**
 * The in-app guide: what each part of the product does and how to use it, in plain words.
 * Topics are data so they are easy to edit; `feature` and `anyOf` hide topics a member's plan or role
 * does not include (the same rules as the navigation).
 */

export type AreaKey = "start" | "clients" | "insurance" | "money" | "team" | "questions";

export interface Area {
  key: AreaKey;
  title: string;
  blurb: string;
}

export interface Topic {
  id: string;
  area: AreaKey;
  title: string;
  summary: string;
  /** In order: these really are steps. */
  steps?: string[];
  tip?: string;
  href?: string;
  linkLabel?: string;
  /** Extra words people might search with. */
  keywords?: string[];
  feature?: string;
  anyOf?: string[];
}

export const AREAS: Area[] = [
  { key: "start", title: "Getting set up", blurb: "Your agency, your brand and your account" },
  { key: "clients", title: "Clients & leads", blurb: "Everyone you serve and everyone you are chasing" },
  { key: "insurance", title: "Quotes, policies & renewals", blurb: "From comparing insurers to keeping the client next year" },
  { key: "money", title: "Invoices & getting paid", blurb: "Invoices, M-Pesa, payments and eTIMS" },
  { key: "team", title: "Team, plan & security", blurb: "Who can do what, and what your plan includes" },
  { key: "questions", title: "Common questions", blurb: "Quick answers" },
];

export const TOPICS: Topic[] = [
  // ---------------------------------------------------------------- getting set up
  {
    id: "agency-details",
    area: "start",
    title: "Fill in your agency details",
    summary: "Your KRA PIN, IRA licence, phone and address print on every quote and invoice.",
    steps: [
      "Open Settings, then Agency profile.",
      "Add your KRA PIN, IRA licence number and expiry, office phone and address.",
      "Save. New documents use the details straight away.",
    ],
    tip: "Clients trust a quote more when your licence number is on it.",
    href: "/settings/organization",
    linkLabel: "Open Agency profile",
    keywords: ["kra pin", "ira licence", "license", "address", "profile", "company"],
    anyOf: ["org:read"],
  },
  {
    id: "brand",
    area: "start",
    title: "Put your logo and colours on documents",
    summary: "Choose a document style, your main colour and a logo. The preview shows a real quotation as you change it.",
    steps: [
      "Open Settings, then Documents & brand.",
      "Pick a style, then your main colour.",
      "Upload your logo (PNG or JPG).",
      "Check the preview and save.",
    ],
    href: "/settings/branding",
    linkLabel: "Open Documents & brand",
    keywords: ["logo", "colour", "color", "template", "style", "pdf look"],
    feature: "branding",
    anyOf: ["branding:manage"],
  },
  {
    id: "numbering",
    area: "start",
    title: "Choose how documents are numbered",
    summary: "Quotes, invoices and credit notes get numbers like QT-2026-00001. You can change the prefix and format.",
    href: "/settings/numbering",
    linkLabel: "Open Document numbers",
    keywords: ["number", "prefix", "sequence", "invoice number", "quote number"],
    anyOf: ["numbering:read"],
  },
  {
    id: "find-anything",
    area: "start",
    title: "Find anything fast",
    summary: "Press ⌘K (Ctrl+K on Windows) anywhere to jump to a page, a setting or a guide topic.",
    steps: ["Press ⌘K or Ctrl+K, or click Search at the top.", "Type a few letters.", "Press Enter to go there."],
    tip: "On this page, press / to jump to the search box.",
    keywords: ["search", "shortcut", "keyboard", "command", "jump"],
  },
  {
    id: "notifications",
    area: "start",
    title: "Know when a client opens what you sent",
    summary: "The bell at the top tells you when a client opens or accepts a quote or invoice you shared.",
    keywords: ["bell", "alert", "opened", "viewed", "notification"],
  },

  // ---------------------------------------------------------------- clients & leads
  {
    id: "add-client",
    area: "clients",
    title: "Add a client",
    summary: "Keep each client's contacts, policies, documents and history in one place.",
    steps: [
      "Open Clients, then Add client.",
      "Type their name and phone. Email, ID and KRA PIN are optional.",
      "Save. If the phone or ID matches someone you already have, you are warned before a duplicate is made.",
    ],
    href: "/clients",
    linkLabel: "Open Clients",
    keywords: ["customer", "new client", "contact", "duplicate", "individual", "company"],
    anyOf: ["client:write"],
  },
  {
    id: "client-page",
    area: "clients",
    title: "Everything about a client, in tabs",
    summary: "Each client has Overview, Timeline, Quotes, Policies, Billing, Documents and Tasks.",
    steps: [
      "Timeline: log calls, visits and WhatsApp chats so you remember what was said.",
      "Documents: upload ID copies, logbooks and KRA PINs, with expiry dates.",
      "Tasks: add follow-ups with a due date.",
    ],
    tip: "Upload PDFs without a password, or colleagues will need the password to open them.",
    href: "/clients",
    linkLabel: "Open Clients",
    keywords: ["timeline", "history", "call log", "documents", "upload", "id copy", "logbook", "kyc"],
    anyOf: ["client:read:all", "client:read:own"],
  },
  {
    id: "search-clients",
    area: "clients",
    title: "Find a client by name or phone",
    summary: "Search understands phone numbers however they are typed: 0712…, +254 712… or 254712….",
    href: "/clients",
    linkLabel: "Open Clients",
    keywords: ["search", "phone", "find"],
    anyOf: ["client:read:all", "client:read:own"],
  },
  {
    id: "leads",
    area: "clients",
    title: "Track leads until they buy",
    summary: "Leads are people you are still chasing. Move them along the pipeline; when one is won, it becomes a client.",
    steps: [
      "Open Leads, then Add lead: name, phone, class of insurance and expected yearly premium.",
      "Use Move to as the conversation goes on.",
      "Move it to Won and the client page opens, with the history kept.",
    ],
    href: "/leads",
    linkLabel: "Open Leads",
    keywords: ["prospect", "pipeline", "sales", "won", "lost", "referral"],
    anyOf: ["lead:read:all", "lead:read:own"],
  },
  {
    id: "tasks",
    area: "clients",
    title: "Follow-ups and to-dos",
    summary: "Tasks keeps everything you promised to do. Overdue tasks show first, and the home page counts them.",
    href: "/tasks",
    linkLabel: "Open Tasks",
    keywords: ["todo", "reminder", "follow up", "due"],
    anyOf: ["task:write", "task:read:all"],
  },

  // ---------------------------------------------------------------- insurance
  {
    id: "insurers",
    area: "insurance",
    title: "Add the insurers and products you sell",
    summary: "Each product has a rate, a minimum premium and your commission, so quotes calculate themselves.",
    steps: [
      "Open Settings, then Insurers & products.",
      "Type the insurer's name, then Add insurer.",
      "Add product: name, rate (%), minimum premium and commission (%).",
    ],
    tip: "Levies (training levy, PCF, stamp duty) are added automatically.",
    href: "/settings/insurers",
    linkLabel: "Open Insurers & products",
    keywords: ["underwriter", "product", "rate", "commission rate", "minimum premium", "levy"],
    feature: "insurance",
    anyOf: ["insurer:read"],
  },
  {
    id: "calculator",
    area: "insurance",
    title: "Compare premiums in seconds",
    summary: "The premium calculator prices the same cover with every insurer, cheapest first, with levies and your commission.",
    steps: ["Open Premium calculator.", "Pick the class and type the sum insured.", "Compare. Only you see the commission."],
    href: "/calculator",
    linkLabel: "Open the calculator",
    keywords: ["price", "premium", "compare", "cheapest", "motor", "sum insured", "levy"],
    feature: "insurance",
    anyOf: ["insurer:read"],
  },
  {
    id: "send-quote",
    area: "insurance",
    title: "Send a quote the client can accept on their phone",
    summary: "Build a quote with one or more insurers, send it by link, WhatsApp or email, and the client accepts the option they want.",
    steps: [
      "Open the client, then New quote.",
      "Tick the products to compare, add the sum insured and what is covered.",
      "Create quote, then Send to client.",
      "Share the link on WhatsApp, or email it.",
      "When the client accepts, the bell tells you and the quote shows which option they chose.",
    ],
    tip: "Clients never see your commission, on the page or in the PDF.",
    href: "/quotes",
    linkLabel: "Open Quotes",
    keywords: ["quotation", "whatsapp", "share", "link", "accept", "pdf", "compare insurers"],
    feature: "insurance",
  },
  {
    id: "policy",
    area: "insurance",
    title: "Turn an accepted quote into a policy",
    summary: "Once the insurer confirms cover and the premium is paid, the accepted option becomes an active policy.",
    steps: [
      "Open the accepted quote, then Create policy.",
      "Tick that the premium has been paid and add the reference.",
      "Tick that the insurer has confirmed cover, then Save policy.",
    ],
    keywords: ["cover", "bind", "active", "debit note", "premium paid"],
    href: "/policies",
    linkLabel: "Open Policies",
    feature: "insurance",
  },
  {
    id: "existing-policy",
    area: "insurance",
    title: "Add policies you sold before",
    summary: "Enter an existing policy by hand so its renewal is tracked, even if it was placed with another insurer.",
    steps: ["Open the client, then Add policy.", "Fill in insurer, what is covered, premium and the cover dates.", "Save policy."],
    href: "/policies/new",
    linkLabel: "Add a policy",
    keywords: ["old policy", "manual", "existing book"],
    feature: "insurance",
  },
  {
    id: "import",
    area: "insurance",
    title: "Import your whole book from Excel",
    summary: "Upload an Excel (.xlsx) or CSV export. Common column names are recognised and rows with problems are shown before anything is saved.",
    steps: [
      "Open Policies, then Import from a spreadsheet.",
      "Choose the file and check the preview.",
      "Fix or leave out the rows with errors, then Import.",
    ],
    tip: "Old .xls files: open them in Excel and save as .xlsx first.",
    href: "/policies/import",
    linkLabel: "Import a spreadsheet",
    keywords: ["excel", "csv", "xlsx", "spreadsheet", "upload", "migrate", "bulk"],
    feature: "book_import",
  },
  {
    id: "renewals",
    area: "insurance",
    title: "Never miss a renewal",
    summary: "Renewals lists every policy ending soon, with a ready WhatsApp message and a one-click renewal quote.",
    steps: [
      "Open Renewals and start with To contact.",
      "Use WhatsApp to message the client, or Quote renewal.",
      "If they leave, mark it Lost with the reason. You can reopen it later.",
    ],
    tip: "Turn on emailed renewal reminders to clients in Agency profile.",
    href: "/renewals",
    linkLabel: "Open Renewals",
    keywords: ["expiry", "expiring", "renew", "retention", "lost", "reminder"],
    feature: "insurance",
  },
  {
    id: "commission",
    area: "insurance",
    title: "Track the commission insurers owe you",
    summary: "See what each insurer owes after 10% withholding tax, record what they pay, and keep the WHT certificates.",
    steps: [
      "Open Commission to see what is owed, by insurer.",
      "Record commission when a statement or payment arrives, with the WHT certificate number.",
    ],
    href: "/commission",
    linkLabel: "Open Commission",
    keywords: ["wht", "withholding", "statement", "earnings", "income"],
    feature: "commission",
    anyOf: ["commission:read:own", "commission:read:all"],
  },

  // ---------------------------------------------------------------- money
  {
    id: "items",
    area: "money",
    title: "Save the things you sell",
    summary: "Items keep your usual services and prices, so invoices take seconds.",
    href: "/settings/items",
    linkLabel: "Open Items & prices",
    keywords: ["product", "service", "catalogue", "price list"],
    anyOf: ["invoice:write"],
  },
  {
    id: "invoice",
    area: "money",
    title: "Send an invoice",
    summary: "Draft, issue and send invoices with VAT worked out for you. Clients open them from a link, no account needed.",
    steps: [
      "Open the client's Billing tab (or Invoices), then New invoice.",
      "Add lines from your items or type them, with any discount.",
      "Save the draft, then Issue. Issued invoices get a number and cannot be edited.",
      "Send: share the link or email it.",
    ],
    tip: "Made a mistake on an issued invoice? Issue a credit note or void it with a reason.",
    href: "/invoices",
    linkLabel: "Open Invoices",
    keywords: ["bill", "vat", "tax invoice", "issue", "send invoice", "pdf"],
    anyOf: ["invoice:write", "invoice:issue"],
  },
  {
    id: "sales-quote",
    area: "money",
    title: "Quote a job, then invoice it in one click",
    summary: "Sales quotes can include optional extras the client chooses. Once accepted, Create invoice copies exactly what they picked.",
    steps: [
      "Open the client's Billing tab, then New sales quote.",
      "Add lines; mark extras as Optional.",
      "Send to client. They tick the extras they want and accept.",
      "Create invoice.",
    ],
    href: "/sales-quotes",
    linkLabel: "Open Sales quotes",
    keywords: ["estimate", "proforma", "optional", "extra", "quotation"],
    anyOf: ["invoice:write"],
  },
  {
    id: "record-payment",
    area: "money",
    title: "Record a payment",
    summary: "Record cash, bank or M-Pesa payments against an invoice. Part payments are fine; overpayments become client credit.",
    steps: ["Open the invoice, then Record payment.", "Enter the amount and reference, then save."],
    href: "/payments",
    linkLabel: "Open Payments",
    keywords: ["receipt", "paid", "part payment", "credit", "overpaid", "bank", "cash"],
    anyOf: ["payment:write"],
  },
  {
    id: "mpesa-connect",
    area: "money",
    title: "Get paid by M-Pesa",
    summary: "Connect your own Paybill or Till. Money goes straight to your account; we never hold it.",
    steps: [
      "Open Settings, then Payments.",
      "Choose Paybill or Till and add the Daraja keys from Safaricom.",
      "Connect M-Pesa. For a Paybill, also register Paybill payments.",
    ],
    tip: "Card payments are coming soon.",
    href: "/settings/payments",
    linkLabel: "Open Payments settings",
    keywords: ["mpesa", "m-pesa", "paybill", "till", "daraja", "safaricom", "stk"],
    anyOf: ["org:read"],
  },
  {
    id: "mpesa-prompt",
    area: "money",
    title: "Send an M-Pesa prompt to the client's phone",
    summary: "The client gets a prompt, enters their PIN, and the invoice is marked paid by itself.",
    steps: ["Open an unpaid invoice.", "Ask for M-Pesa payment, check the number, then Send prompt.", "Wait for the confirmation."],
    tip: "Clients can also pay from the invoice link with Pay with M-Pesa.",
    href: "/invoices",
    linkLabel: "Open Invoices",
    keywords: ["mpesa", "m-pesa", "stk push", "prompt", "pin", "pay now"],
    anyOf: ["payment:write"],
  },
  {
    id: "mpesa-match",
    area: "money",
    title: "Match Paybill payments",
    summary: "Payments with the invoice's payment reference are matched by themselves. The rest wait under M-Pesa payments to match.",
    href: "/payments",
    linkLabel: "Open Payments",
    keywords: ["unmatched", "c2b", "account number", "reference", "paybill"],
    anyOf: ["payment:write"],
  },
  {
    id: "etims",
    area: "money",
    title: "Record KRA eTIMS details",
    summary: "Optional. Turn it on and each issued invoice gets a place for the eTIMS CU number and verification link from your own eTIMS tool.",
    steps: ["Open Settings, then Tax & eTIMS.", "Turn on Record eTIMS on invoices.", "On each issued invoice, add the CU number and save."],
    href: "/settings/tax",
    linkLabel: "Open Tax & eTIMS",
    keywords: ["kra", "etims", "tims", "tax", "cu number", "vat"],
    feature: "etims",
    anyOf: ["org:read"],
  },

  // ---------------------------------------------------------------- team, plan, security
  {
    id: "invite",
    area: "team",
    title: "Invite your team",
    summary: "Invite colleagues by email and give each a role: Admin, Agent, Accounts, Assistant or Viewer.",
    steps: ["Open Settings, then Team.", "Invite by email and choose a role.", "They accept from the email and sign up."],
    tip: "Agents only see their own clients and their own commission.",
    href: "/settings/members",
    linkLabel: "Open Team",
    keywords: ["staff", "user", "colleague", "role", "permission", "seat", "invite"],
    feature: "team",
    anyOf: ["member:read"],
  },
  {
    id: "roles",
    area: "team",
    title: "What each role can do",
    summary:
      "Owner: everything. Admin: everything except billing. Agent: their own clients and commission. Accounts: money and commission. Assistant: clients, documents and tasks. Viewer: read only.",
    keywords: ["role", "access", "permission", "owner", "admin", "agent", "accounts", "assistant", "viewer"],
  },
  {
    id: "plan",
    area: "team",
    title: "Your plan and paying for it",
    summary: "See your plan, what you have used this month, and pay by M-Pesa. Nothing renews by itself.",
    steps: ["Open Settings, then Plan & billing.", "Choose monthly or yearly (2 months free).", "Choose a plan and approve the M-Pesa prompt."],
    tip: "The first 100 paying agencies get half price for 12 months.",
    href: "/settings/plan",
    linkLabel: "Open Plan & billing",
    keywords: ["subscription", "price", "upgrade", "trial", "billing", "founding", "renew"],
    anyOf: ["org:read"],
  },
  {
    id: "two-factor",
    area: "team",
    title: "Protect your account with two-factor sign-in",
    summary: "Add a code from an authenticator app when you sign in, so a stolen password is not enough.",
    steps: [
      "Open Settings, then Security.",
      "Turn on two-factor and scan the code with Google Authenticator or Authy.",
      "Save the backup codes somewhere safe.",
    ],
    href: "/settings/security",
    linkLabel: "Open Security",
    keywords: ["2fa", "mfa", "authenticator", "security", "password", "otp"],
  },

  // ---------------------------------------------------------------- questions
  {
    id: "faq-pdf-password",
    area: "questions",
    title: "A document asks for a password",
    summary:
      "The file was password-protected before it was uploaded (bank and M-Pesa statements often use the owner's ID number). Upload a copy without the password: open it, then Print and Save as PDF.",
    keywords: ["password", "locked", "encrypted", "pdf", "cannot open"],
  },
  {
    id: "faq-edit-issued",
    area: "questions",
    title: "Why can't I edit an issued invoice?",
    summary:
      "Issued invoices are a financial record, so they never change. Issue a credit note for part of it, or void it with a reason and issue a new one.",
    keywords: ["edit", "change", "mistake", "wrong", "credit note", "void", "cancel"],
  },
  {
    id: "faq-commission-hidden",
    area: "questions",
    title: "Can clients see my commission?",
    summary: "No. Commission appears only inside the app for people allowed to see it, never on client pages or PDFs.",
    keywords: ["commission", "private", "hidden", "client view"],
  },
  {
    id: "faq-money",
    area: "questions",
    title: "Where does M-Pesa money go?",
    summary: "Straight to your own Paybill or Till. The app records the payment; it never holds your money.",
    keywords: ["money", "funds", "settlement", "paybill", "safe"],
  },
  {
    id: "faq-lapsed",
    area: "questions",
    title: "What happens if my plan lapses?",
    summary:
      "You get 7 days of grace with everything working. After that the account is read-only: you can still see and download everything, and pay to unlock it. Nothing is deleted.",
    keywords: ["expired", "read only", "lapsed", "unpaid", "grace", "locked"],
  },
  {
    id: "faq-whatsapp",
    area: "questions",
    title: "Can I send quotes and invoices on WhatsApp?",
    summary: "Yes. Every quote and invoice you send has a link and a Share on WhatsApp button. The client opens it on their phone without an account.",
    keywords: ["whatsapp", "share", "link", "phone"],
  },
];

// ---------------------------------------------------------------- visibility and search

export function canSee(topic: Topic, permissions: readonly string[], features: readonly string[]): boolean {
  const featureOk = !topic.feature || features.includes(topic.feature) || features.includes("*");
  const roleOk = !topic.anyOf || topic.anyOf.some((p) => permissions.includes(p));
  return featureOk && roleOk;
}

/** Words that mean the same thing to our users. */
const SYNONYMS: Record<string, string[]> = {
  bill: ["invoice"],
  receipt: ["payment"],
  pay: ["payment", "mpesa"],
  customer: ["client"],
  quotation: ["quote"],
  staff: ["team", "invite"],
  user: ["team", "invite"],
  logo: ["brand"],
  renew: ["renewal"],
  expiry: ["renewal"],
  tax: ["etims", "vat"],
  excel: ["import"],
};

/** Lower case, accents removed, and "M-Pesa" / "m pesa" / "mpesa" made the same. */
export function normalise(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFKD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/m[\s-]?pesa/g, "mpesa")
    .replace(/[^a-z0-9%]+/g, " ")
    .trim();
}

export function queryTerms(query: string): string[] {
  return normalise(query)
    .split(" ")
    .filter((t) => t.length > 1 || /\d/.test(t));
}

function termScore(term: string, topic: Topic): number {
  const words = (s: string) => normalise(s).split(" ");
  const hit = (s: string) => words(s).some((w) => w.startsWith(term));
  if (hit(topic.title)) return 5;
  if ((topic.keywords ?? []).some(hit)) return 4;
  if (hit(topic.summary)) return 2;
  if ((topic.steps ?? []).some(hit) || (topic.tip && hit(topic.tip))) return 1;
  return 0;
}

/** Every term (or one of its synonyms) must match; better matches rank higher. Empty query: no ranking. */
export function searchTopics(topics: readonly Topic[], query: string): Topic[] {
  const terms = queryTerms(query);
  if (!terms.length) return [...topics];
  const scored: { topic: Topic; score: number }[] = [];
  for (const topic of topics) {
    let total = 0;
    let all = true;
    for (const term of terms) {
      const best = Math.max(termScore(term, topic), ...(SYNONYMS[term] ?? []).map((s) => termScore(s, topic) - 0.5));
      if (best <= 0) {
        all = false;
        break;
      }
      total += best;
    }
    if (all) scored.push({ topic, score: total });
  }
  return scored.sort((a, b) => b.score - a.score).map((s) => s.topic);
}
