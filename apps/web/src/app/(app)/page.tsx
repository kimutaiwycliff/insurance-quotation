import { KeyRound, Palette, UserPlus } from "lucide-react";
import Link from "next/link";
import { getTranslations } from "next-intl/server";

import { Seal } from "@/components/brand/seal";
import type { Dashboard } from "@/lib/api/generated/model";
import { formatMoney } from "@/lib/format";
import type { Me } from "@/lib/me";
import { serverApi } from "@/lib/server/api";
import { cn } from "@/lib/utils";

function Stat({ href, value, label, urgent }: { href: string; value: number; label: string; urgent?: boolean }) {
  return (
    <Link href={href} className="grid gap-1 rounded-lg border bg-card px-4 py-3 hover:border-primary">
      <span className={cn("tabular font-heading text-3xl", urgent && value > 0 && "text-destructive")}>{value}</span>
      <span className="text-sm text-muted-foreground">{label}</span>
    </Link>
  );
}

const MONTH_LETTERS = ["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"];

function BookYear({ board }: { board: Dashboard }) {
  const b = board.book;
  const money = (a: string) => formatMoney(a, b.currency);
  const closed = b.renewed + b.lost;
  // Bar heights are a display proportion only; money itself is never computed as a float.
  const whole = (a: string) => Number(a.split(".")[0]);
  const max = Math.max(...b.written_by_month.map((m) => whole(m.amount)), 0);
  const figures = [
    { label: `Premium written (${b.written_count} ${b.written_count === 1 ? "policy" : "policies"})`, value: money(b.written_premium) },
    { label: "Premium clients still owe", value: money(b.outstanding_premium), href: "/policies" },
    ...(b.expected_commission !== null && board.commission_received !== null
      ? [
          { label: "Commission expected", value: money(b.expected_commission), href: "/commission" },
          { label: "Commission received", value: money(board.commission_received), href: "/commission" },
        ]
      : []),
    { label: "Renewals kept, last 12 months", value: closed ? `${Math.round((b.renewed / closed) * 100)}% (${b.renewed} of ${closed})` : "None yet", href: "/renewals" },
  ];
  return (
    <section aria-labelledby="year-heading" className="grid gap-3">
      <h2 id="year-heading" className="text-xl">This year</h2>
      <dl className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {figures.map((f) => (
          <div key={f.label} className="grid content-start gap-1 rounded-lg border bg-card px-4 py-3">
            <dt className="text-sm text-muted-foreground">{f.href ? <Link href={f.href} className="hover:underline">{f.label}</Link> : f.label}</dt>
            <dd className="tabular font-heading text-xl">{f.value}</dd>
          </div>
        ))}
      </dl>
      {max > 0 && (
        <figure className="grid gap-1">
          <figcaption className="text-sm text-muted-foreground">Premium written by month, last 12 months</figcaption>
          <ol className="grid h-24 grid-cols-12 items-end gap-1 border-b sm:gap-2">
            {b.written_by_month.map((m) => (
              <li key={m.month} className="flex h-full items-end" aria-label={`${m.month}: ${money(m.amount)}`}>
                <span className="w-full rounded-t-sm bg-primary" style={{ height: `${Math.max(Math.round((whole(m.amount) / max) * 100), whole(m.amount) > 0 ? 3 : 0)}%` }} />
              </li>
            ))}
          </ol>
          <ol aria-hidden="true" className="grid grid-cols-12 gap-1 text-center text-xs text-muted-foreground sm:gap-2">
            {b.written_by_month.map((m) => <li key={m.month}>{MONTH_LETTERS[Number(m.month.slice(5)) - 1]}</li>)}
          </ol>
        </figure>
      )}
    </section>
  );
}

export default async function HomePage() {
  const t = await getTranslations("home");
  const leadsT = await getTranslations("leads");
  const me = await serverApi<Me>("/api/v1/me");
  const board = await serverApi<Dashboard>("/api/v1/dashboard");
  const firstName = (me.name || me.email).split(" ")[0];
  const setup = [
    { href: "/settings/branding", label: t("branding"), icon: Palette, show: me.permissions.includes("branding:manage") },
    { href: "/settings/members", label: t("team"), icon: UserPlus, show: me.role === "owner" || me.role === "admin" },
    { href: "/settings/security", label: t("security"), icon: KeyRound, show: !me.mfa_enrolled },
  ].filter((s) => s.show);
  const pipeline = board.pipeline?.stages.filter((s) => ["new", "contacted", "quoted"].includes(s.stage)) ?? [];

  return (
    <div className="grid gap-8">
      <div className="flex items-center gap-5">
        <Seal name={me.tenant.name} size={72} className="hidden text-primary sm:block" />
        <div>
          <h1 className="text-3xl sm:text-4xl">{t("greeting", { name: firstName ?? "" })}</h1>
          {board.clients === 0 && <p className="mt-2 max-w-prose text-lg text-muted-foreground">{t("body")}</p>}
        </div>
      </div>

      <section aria-label="Today" className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        {board.tasks && <Stat href="/tasks" value={board.tasks.overdue} label={t("tasksOverdue")} urgent />}
        {board.tasks && <Stat href="/tasks" value={board.tasks.today} label={t("tasksToday")} />}
        {board.pipeline && <Stat href="/leads" value={board.pipeline.follow_ups_due} label={t("followUps")} urgent />}
        <Stat href="/renewals" value={board.renewals_due_30d} label={t("renewalsDue")} urgent />
        {board.premiums_to_remit > 0 && <Stat href="/tasks" value={board.premiums_to_remit} label={t("toRemit")} urgent />}
        <Stat href="/policies" value={board.policies_active} label={t("activePolicies")} />
        <Stat href="/clients" value={board.new_clients_30d} label={t("newClients")} />
        {board.documents_expiring_30d > 0 && <Stat href="/clients" value={board.documents_expiring_30d} label={t("expiring")} urgent />}
      </section>

      {(board.policies_active > 0 || board.book.written_count > 0) && <BookYear board={board} />}

      {pipeline.length > 0 && (
        <section aria-labelledby="pipeline-heading" className="grid gap-3">
          <h2 id="pipeline-heading" className="text-xl">{t("pipeline")}</h2>
          <ol className="grid gap-2 sm:grid-cols-3">
            {pipeline.map((s) => (
              <li key={s.stage}>
                <Link href="/leads" className="flex items-baseline justify-between gap-3 border-l-[3px] border-maize bg-card px-4 py-3 hover:bg-accent">
                  <span><span className="font-bold">{leadsT(s.stage)}</span> <span className="tabular text-muted-foreground">{s.count}</span></span>
                  <span className="tabular text-sm">{formatMoney(s.estimated_premium.amount, s.estimated_premium.currency)}</span>
                </Link>
              </li>
            ))}
          </ol>
        </section>
      )}

      {setup.length > 0 && (
        <ul className="grid gap-2 sm:max-w-md">
          {setup.map(({ href, label, icon: Icon }) => (
            <li key={href}>
              <Link href={href} className="flex items-center gap-3 rounded-md border bg-card px-4 py-3 font-bold hover:border-primary">
                <Icon className="size-5 text-primary" aria-hidden="true" />
                {label}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
