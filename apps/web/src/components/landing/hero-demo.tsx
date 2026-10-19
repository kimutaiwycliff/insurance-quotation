"use client";

import { BellRing, CheckCheck, RotateCcw } from "lucide-react";
import { useState, type CSSProperties } from "react";

/** Delay for one step of the sequence, read by the lp-* animations in landing.css. */
function at(seconds: number): CSSProperties {
  return { "--d": `${seconds}s` } as CSSProperties;
}

// Example insurers and figures: rate on a KES 2,500,000 sum insured, plus training levy 0.2%, PHCF 0.25% and
// KES 40 stamp duty (the Kenyan pack's rules).
const OPTIONS = [
  { insurer: "Mlima General", note: "Excess KES 25,000", total: "87,933.75", recommended: false },
  {
    insurer: "Pwani Assurance",
    note: "Windscreen and radio included",
    total: "100,490.00",
    recommended: true,
  },
  {
    insurer: "Baobab Insurance",
    note: "Courtesy car for 10 days",
    total: "106,768.13",
    recommended: false,
  },
];

/**
 * The hero's one orchestrated moment: the agent shares a comparison quote on WhatsApp, the client accepts it and
 * the stamp comes down. Plays once; "Play again" remounts the figure to replay it. Every text is real markup, so
 * screen readers and reduced-motion visitors get the finished story.
 */
export function HeroDemo() {
  const [run, setRun] = useState(0);
  return (
    <div className="grid gap-3">
      <figure key={run} className="lp-demo grid gap-3" aria-labelledby="demo-caption">
        <div className="lp-bubble flex justify-end" style={at(0.2)}>
          <div className="max-w-[19rem] rounded-2xl rounded-br-sm bg-[#d9f2e3] px-4 py-3 text-[0.95rem] text-[#10241f] shadow-sm dark:bg-[#1f4a3d] dark:text-[#e8efec]">
            <p>
              Hi Achieng, your car insurance options are ready. Compare them and accept the one you
              like.
            </p>
            <p className="text-acacia mt-2 rounded-lg bg-white/70 px-3 py-2 text-sm font-bold dark:bg-black/20 dark:text-[#7fd6c2]">
              Open your quote
            </p>
            <p className="text-muted-foreground mt-1 flex items-center justify-end gap-1 text-xs">
              09:41
              <CheckCheck
                aria-hidden="true"
                className="lp-ticks size-4 text-[#1d8fd8]"
                style={at(0.9)}
              />
            </p>
          </div>
        </div>

        <div
          className="lp-in bg-card relative rounded-xl border p-4 shadow-[0_18px_40px_-24px_rgb(23_48_43/0.45)] sm:p-5"
          style={at(1.2)}
        >
          <p className="font-heading pr-20 text-lg leading-tight font-bold sm:pr-24">
            Comprehensive motor, private car
          </p>
          <p className="text-muted-foreground pr-20 text-sm sm:pr-24">
            KCX 214T, sum insured KES 2,500,000, for Achieng Otieno
          </p>
          <ul className="mt-4 grid gap-1.5">
            {OPTIONS.map((option, index) => (
              <li
                key={option.insurer}
                className={
                  option.recommended
                    ? "lp-in lp-mark flex items-baseline justify-between gap-3 rounded-md bg-[color-mix(in_oklab,var(--maize)_16%,transparent)] px-3 py-2 shadow-[inset_4px_0_0_var(--maize)]"
                    : "lp-in flex items-baseline justify-between gap-3 rounded-md px-3 py-2"
                }
                style={
                  option.recommended
                    ? ({ ...at(1.4 + index * 0.2), "--d2": "2.4s" } as CSSProperties)
                    : at(1.4 + index * 0.2)
                }
              >
                <span className="min-w-0">
                  <span className="block font-bold">
                    {option.insurer}
                    {option.recommended && (
                      <span className="dark:text-maize ml-2 text-xs font-bold text-[#7a5a00]">
                        Recommended
                      </span>
                    )}
                  </span>
                  <span className="text-muted-foreground block text-xs">{option.note}</span>
                </span>
                <span className="tabular shrink-0 font-bold">KES {option.total}</span>
              </li>
            ))}
          </ul>
          <p className="mt-4 flex items-center justify-between gap-3">
            <span className="text-muted-foreground text-xs">Levies and stamp duty included</span>
            <span
              className="lp-press bg-primary text-primary-foreground inline-flex h-10 items-center rounded-md px-4 text-sm font-bold"
              style={at(3.0)}
            >
              Accept Pwani Assurance
            </span>
          </p>
          <svg
            viewBox="0 0 120 120"
            aria-hidden="true"
            className="lp-stamp pointer-events-none absolute -top-7 -right-3 size-24 sm:-right-5 sm:size-28"
            style={at(3.4)}
          >
            <defs>
              <path id="lp-ring" d="M60,60 m-44,0 a44,44 0 1,1 88,0 a44,44 0 1,1 -88,0" />
            </defs>
            <circle cx="60" cy="60" r="56" fill="none" stroke="currentColor" strokeWidth="4" />
            <circle cx="60" cy="60" r="36" fill="none" stroke="currentColor" strokeWidth="2" />
            <text fontSize="11" fontWeight="800" fill="currentColor" letterSpacing="1">
              <textPath href="#lp-ring" textLength="268" lengthAdjust="spacing">
                ACCEPTED • PWANI ASSURANCE • ACCEPTED •
              </textPath>
            </text>
            <path
              d="M44 61 l11 11 l22 -24"
              fill="none"
              stroke="currentColor"
              strokeWidth="7"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </div>

        <p
          className="lp-in bg-ink flex items-start gap-2 rounded-lg px-4 py-3 text-sm text-[#f6f7f4] dark:bg-[#1d3631]"
          style={at(4.0)}
        >
          <BellRing aria-hidden="true" className="text-maize mt-0.5 size-4 shrink-0" />
          <span>
            Achieng accepted Pwani Assurance. Policy created, renewal reminder set for 19 Oct 2027.
          </span>
        </p>
        <figcaption id="demo-caption" className="text-muted-foreground text-xs">
          Example: a quote shared on WhatsApp and accepted by the client. Insurers and figures are
          illustrative.
        </figcaption>
      </figure>
      <button
        type="button"
        onClick={() => setRun((n) => n + 1)}
        className="text-acacia inline-flex items-center gap-1.5 justify-self-start rounded-md px-2 py-1 text-sm font-bold underline-offset-4 hover:underline dark:text-[#7fd6c2]"
      >
        <RotateCcw aria-hidden="true" className="size-4" /> Play again
      </button>
    </div>
  );
}
