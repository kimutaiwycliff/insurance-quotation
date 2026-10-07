import { cn } from "@/lib/utils";

/** Initials of an agency name: "Wanjiku Insurance Agency" → "WI". */
export function initials(name: string): string {
  const words = name
    .replace(/[^\p{L}\p{N}\s]/gu, " ")
    .split(/\s+/)
    .filter((w) => w && !/^(and|&|of|the|ltd|limited)$/i.test(w));
  return (words.length > 1 ? `${words[0]![0]}${words[1]![0]}` : (words[0] ?? "?").slice(0, 2)).toUpperCase();
}

/**
 * The agency's stamp: a circular seal like the rubber stamps on Kenyan cover notes and receipts.
 * Purely decorative (aria-hidden); the agency name is always also rendered as text nearby.
 */
export function Seal({
  name,
  size = 44,
  className,
}: {
  name: string;
  size?: number;
  className?: string;
}) {
  const ring = (name || "Your agency").toUpperCase().slice(0, 40);
  const id = `seal-${ring.replace(/[^A-Z0-9]/g, "")}-${size}`;
  return (
    <svg
      viewBox="0 0 100 100"
      width={size}
      height={size}
      aria-hidden="true"
      className={cn("shrink-0 -rotate-6 text-maize", className)}
    >
      <circle cx="50" cy="50" r="47" fill="none" stroke="currentColor" strokeWidth="3" />
      <circle cx="50" cy="50" r="33" fill="none" stroke="currentColor" strokeWidth="1.5" />
      <path id={id} d="M50,50 m-40,0 a40,40 0 1,1 80,0 a40,40 0 1,1 -80,0" fill="none" />
      {size >= 64 && (
        <text fontSize="8.5" fill="currentColor" fontWeight="700">
          {/* The name once, stretched to go exactly round the ring (~251 units of circumference). */}
          <textPath href={`#${id}`} startOffset="0" textLength="240" lengthAdjust="spacing">
            {`${ring} •`}
          </textPath>
        </text>
      )}
      <text
        x="50"
        y="50"
        dominantBaseline="central"
        textAnchor="middle"
        fontSize="28"
        fontWeight="800"
        fill="currentColor"
        style={{ fontFamily: "var(--font-display)" }}
      >
        {initials(name || "?")}
      </text>
    </svg>
  );
}
