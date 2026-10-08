/** Locale-aware formatting. Money comes from the API as strings and is never parsed into floats for maths. */

const LOCALE = "en-KE";
const MINOR_UNITS: Record<string, number> = { KES: 2, UGX: 0, TZS: 2, RWF: 0, BIF: 0, USD: 2, EUR: 2, GBP: 2, JPY: 0, BHD: 3, KWD: 3 };

/** "1234.5" KES → "KES 1,234.50". Formatting only; amounts are already rounded by the API. */
export function formatMoney(amount: string, currency: string): string {
  const digits = MINOR_UNITS[currency] ?? 2;
  const [whole = "0", fraction = ""] = amount.replace(/^-/, "").split(".");
  const grouped = new Intl.NumberFormat(LOCALE).format(BigInt(whole));
  const decimals = digits ? `.${fraction.padEnd(digits, "0").slice(0, digits)}` : "";
  return `${amount.startsWith("-") ? "-" : ""}${currency} ${grouped}${decimals}`;
}

export function formatDate(value: string | Date): string {
  return new Intl.DateTimeFormat(LOCALE, { day: "numeric", month: "short", year: "numeric", timeZone: "Africa/Nairobi" }).format(
    typeof value === "string" ? new Date(value) : value,
  );
}

export function relativeTime(value: string | Date, now: Date = new Date()): string {
  const date = typeof value === "string" ? new Date(value) : value;
  const seconds = Math.round((date.getTime() - now.getTime()) / 1000);
  const rtf = new Intl.RelativeTimeFormat(LOCALE, { numeric: "auto" });
  const units: [Intl.RelativeTimeFormatUnit, number][] = [["day", 86400], ["hour", 3600], ["minute", 60]];
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return rtf.format(Math.round(seconds / size), unit);
  }
  return rtf.format(seconds, "second");
}

/** "+254712345678" → "0712 345 678" for Kenyan numbers; other numbers stay international. */
export function formatPhone(e164: string | null | undefined): string | null {
  if (!e164) return null;
  const ke = e164.match(/^\+254(\d{3})(\d{3})(\d{3})$/);
  return ke ? `0${ke[1]} ${ke[2]} ${ke[3]}` : e164;
}

/** wa.me link (digits only, no plus). */
export function whatsappLink(e164: string): string {
  return `https://wa.me/${e164.replace(/\D/g, "")}`;
}
