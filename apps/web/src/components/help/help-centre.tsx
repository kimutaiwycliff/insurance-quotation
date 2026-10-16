"use client";

import { ArrowRight, ChevronDown, Lightbulb, Search, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { SetupStampCard } from "@/components/help/setup-stamp-card";
import { AREAS, TOPICS, canSee, queryTerms, searchTopics, type AreaKey, type Topic } from "@/components/help/topics";
import { useMe } from "@/components/shell/me-context";
import { cn } from "@/lib/utils";

const EXAMPLES = [
  "How do I send a quote on WhatsApp?",
  "Get paid by M-Pesa",
  "Import my policies from Excel",
  "Who can see my commission?",
  "Fix a mistake on an invoice",
  "Add my logo",
];
const TRY = ["M-Pesa", "renewals", "invoice", "import", "team"];

function escapeRegExp(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Marks the words that matched the search (start of a word, any case; "mpesa" also marks "M-Pesa"). */
function Highlight({ text, terms }: { text: string; terms: string[] }) {
  if (!terms.length) return <>{text}</>;
  const parts = terms.map((t) => (t === "mpesa" ? "m[\\s-]?pesa" : escapeRegExp(t)));
  const pattern = new RegExp(`(?<![\\p{L}\\p{N}])(${parts.join("|")})`, "giu");
  const out: ReactNode[] = [];
  let last = 0;
  for (const match of text.matchAll(pattern)) {
    const start = match.index ?? 0;
    out.push(text.slice(last, start));
    out.push(
      <mark key={start} className="rounded-sm bg-maize/45 px-0.5 text-inherit">
        {match[0]}
      </mark>,
    );
    last = start + match[0].length;
  }
  out.push(text.slice(last));
  return <>{out}</>;
}

function TopicItem({ topic, open, onToggle, terms, level = 3 }: { topic: Topic; open: boolean; onToggle: () => void; terms: string[]; level?: 3 | 4 }) {
  const Heading = level === 3 ? "h3" : "h4";
  const panelId = `topic-${topic.id}-panel`;
  return (
    <li id={`topic-${topic.id}`} className={cn("help-rise scroll-mt-24 rounded-lg border bg-card transition-colors", open && "border-primary")}>
      <Heading className="text-base font-normal">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={onToggle}
          className="flex w-full items-start gap-3 rounded-lg px-4 py-3 text-left hover:bg-accent/60"
        >
          <span className="grid flex-1 gap-0.5">
            <span className="font-heading text-[1.05rem] font-semibold">
              <Highlight text={topic.title} terms={terms} />
            </span>
            <span className="text-sm text-muted-foreground">
              <Highlight text={topic.summary} terms={terms} />
            </span>
          </span>
          <ChevronDown aria-hidden="true" className={cn("mt-1 size-5 shrink-0 text-muted-foreground transition-transform duration-300", open && "rotate-180")} />
        </button>
      </Heading>
      <div id={panelId} role="region" aria-label={topic.title} className="help-collapse" data-open={open} inert={!open}>
        <div className="overflow-hidden">
          <div className="grid gap-4 px-4 pb-4">
            {topic.steps && (
              <ol className="grid gap-2">
                {topic.steps.map((step, i) => (
                  <li key={step} className="flex gap-3">
                    <span aria-hidden="true" className="grid size-6 shrink-0 place-items-center rounded-full bg-primary text-xs font-bold text-primary-foreground">
                      {i + 1}
                    </span>
                    <span>
                      <Highlight text={step} terms={terms} />
                    </span>
                  </li>
                ))}
              </ol>
            )}
            {topic.tip && (
              <p className="flex gap-2 rounded-md bg-maize/15 px-3 py-2 text-sm">
                <Lightbulb aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
                <span>
                  <Highlight text={topic.tip} terms={terms} />
                </span>
              </p>
            )}
            {topic.href && (
              <Link href={topic.href} className="group inline-flex w-fit items-center gap-1.5 font-bold text-primary underline-offset-4 hover:underline">
                {topic.linkLabel ?? "Take me there"}
                <ArrowRight aria-hidden="true" className="size-4 transition-transform group-hover:translate-x-0.5" />
              </Link>
            )}
          </div>
        </div>
      </div>
    </li>
  );
}

export function HelpCentre() {
  const me = useMe();
  const permissions = me.permissions as string[];
  const visible = useMemo(() => TOPICS.filter((t) => canSee(t, permissions, me.features)), [permissions, me.features]);
  const [query, setQuery] = useState("");
  const [area, setArea] = useState<AreaKey | "all">("all");
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [example, setExample] = useState(0);
  const [focused, setFocused] = useState(false);
  const input = useRef<HTMLInputElement>(null);

  // Deep links: /help?q=mpesa and /help#topic-send-quote.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const q = params.get("q");
    const id = window.location.hash.replace(/^#topic-/, "");
    const frame = window.requestAnimationFrame(() => {
      if (q) setQuery(q);
      if (id && TOPICS.some((t) => t.id === id)) {
        setOpen(new Set([id]));
        document.getElementById(`topic-${id}`)?.scrollIntoView({ block: "start" });
      }
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  // "/" jumps to the search box (unless typing somewhere already).
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement;
      if (e.key !== "/" || target.closest("input, textarea, select, [contenteditable=true]")) return;
      e.preventDefault();
      input.current?.focus();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // The example question in the search box changes every few seconds while it is empty and not focused.
  useEffect(() => {
    if (query || focused || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const timer = window.setInterval(() => setExample((i) => (i + 1) % EXAMPLES.length), 3200);
    return () => window.clearInterval(timer);
  }, [query, focused]);

  const terms = queryTerms(query);
  const searching = terms.length > 0;
  const results = useMemo(() => {
    const found = searchTopics(visible, query);
    return area === "all" ? found : found.filter((t) => t.area === area);
  }, [visible, query, area]);

  function toggle(id: string) {
    setOpen((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      window.history.replaceState(null, "", next.has(id) ? `#topic-${id}` : window.location.pathname + window.location.search);
      return next;
    });
  }

  const areasShown = AREAS.filter((a) => visible.some((t) => t.area === a.key));
  const counts = Object.fromEntries(areasShown.map((a) => [a.key, visible.filter((t) => t.area === a.key).length]));

  return (
    <div className="grid gap-8">
      <header className="help-hero relative grid gap-5 overflow-hidden rounded-xl border bg-card px-5 py-7 sm:px-8 sm:py-9">
        <div className="grid max-w-2xl gap-2">
          <h1 className="text-3xl sm:text-4xl">Help & guide</h1>
          <p className="text-lg text-muted-foreground">Everything this app can do for your agency, and how. Ask it like you would ask a colleague.</p>
        </div>
        <div className="relative max-w-2xl">
          <label htmlFor="help-search" className="sr-only">
            Search the guide
          </label>
          <Search aria-hidden="true" className="pointer-events-none absolute top-1/2 left-4 size-5 -translate-y-1/2 text-muted-foreground" />
          <input
            ref={input}
            id="help-search"
            type="search"
            autoComplete="off"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)}
            className="h-14 w-full rounded-full border-2 border-input bg-background pr-24 pl-12 text-lg shadow-sm transition-colors outline-none focus:border-primary"
          />
          {!query && (
            <span key={example} aria-hidden="true" className="help-placeholder pointer-events-none absolute top-1/2 left-12 -translate-y-1/2 truncate pr-24 text-lg text-muted-foreground" style={{ maxWidth: "calc(100% - 3rem)" }}>
              {EXAMPLES[example]}
            </span>
          )}
          {query ? (
            <button type="button" onClick={() => { setQuery(""); input.current?.focus(); }} aria-label="Clear search" className="absolute top-1/2 right-3 grid size-9 -translate-y-1/2 place-items-center rounded-full hover:bg-accent">
              <X className="size-5" />
            </button>
          ) : (
            <kbd aria-hidden="true" className="absolute top-1/2 right-4 hidden -translate-y-1/2 rounded border bg-muted px-2 py-0.5 text-sm text-muted-foreground sm:block">
              /
            </kbd>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-muted-foreground">Try</span>
          {TRY.map((t) => (
            <button key={t} type="button" onClick={() => setQuery(t)} className="rounded-full border bg-background px-3 py-1 transition-colors hover:border-primary hover:text-primary">
              {t}
            </button>
          ))}
        </div>
      </header>

      {!searching && <SetupStampCard />}

      <section aria-labelledby="topics-heading" className="grid gap-4">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <h2 id="topics-heading" className="text-2xl">
            {searching ? "Results" : "Browse by area"}
          </h2>
          <p role="status" aria-live="polite" className="text-sm text-muted-foreground">
            {searching ? `${results.length} ${results.length === 1 ? "topic matches" : "topics match"} “${query.trim()}”` : `${visible.length} topics`}
          </p>
        </div>
        <div role="radiogroup" aria-label="Area" className="-mx-4 flex gap-2 overflow-x-auto px-4 pb-1 sm:mx-0 sm:flex-wrap sm:px-0">
          {[{ key: "all" as const, title: "All" }, ...areasShown].map((a) => (
            <button
              key={a.key}
              type="button"
              role="radio"
              aria-checked={area === a.key}
              onClick={() => setArea(a.key)}
              className={cn(
                "shrink-0 rounded-full border px-3.5 py-1.5 text-sm whitespace-nowrap transition-colors",
                area === a.key ? "border-primary bg-primary font-bold text-primary-foreground" : "bg-card hover:border-primary",
              )}
            >
              {a.title}
              {a.key !== "all" && <span className={cn("ml-1.5 tabular", area === a.key ? "opacity-80" : "text-muted-foreground")}>{counts[a.key]}</span>}
            </button>
          ))}
        </div>

        {results.length === 0 ? (
          <div className="help-rise grid justify-items-start gap-3 rounded-lg border border-dashed px-5 py-8">
            <p className="text-lg">Nothing matches “{query.trim()}” yet.</p>
            <p className="text-muted-foreground">Try fewer words, or one of these:</p>
            <div className="flex flex-wrap gap-2">
              {TRY.map((t) => (
                <button key={t} type="button" onClick={() => setQuery(t)} className="rounded-full border bg-card px-3 py-1 text-sm hover:border-primary">
                  {t}
                </button>
              ))}
            </div>
          </div>
        ) : searching ? (
          <ul key={query} className="grid gap-2">
            {results.map((t) => (
              <TopicItem key={t.id} topic={t} open={open.has(t.id)} onToggle={() => toggle(t.id)} terms={terms} />
            ))}
          </ul>
        ) : (
          <div key={area} className="grid gap-8">
            {areasShown
              .filter((a) => area === "all" || a.key === area)
              .map((a) => (
                <section key={a.key} aria-labelledby={`area-${a.key}`} className="grid gap-3">
                  <div>
                    <h3 id={`area-${a.key}`} className="text-xl">
                      {a.title}
                    </h3>
                    <p className="text-sm text-muted-foreground">{a.blurb}</p>
                  </div>
                  <ul className="grid gap-2">
                    {results
                      .filter((t) => t.area === a.key)
                      .map((t) => (
                        <TopicItem key={t.id} topic={t} open={open.has(t.id)} onToggle={() => toggle(t.id)} terms={terms} level={4} />
                      ))}
                  </ul>
                </section>
              ))}
          </div>
        )}
      </section>
    </div>
  );
}
