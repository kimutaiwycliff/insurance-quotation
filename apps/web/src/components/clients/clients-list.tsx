"use client";

import { useInfiniteQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Search } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { ClientForm, toPayload } from "@/components/clients/client-form";
import { useCan } from "@/components/shell/me-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";
import { clientsCreate, clientsList, getClientsListQueryKey } from "@/lib/api/generated/clients/clients";
import { formatPhone } from "@/lib/format";
import { useDebounced } from "@/lib/use-debounced";

export function ClientsList() {
  const t = useTranslations("clients");
  const router = useRouter();
  const queryClient = useQueryClient();
  const canWrite = useCan("client:write");
  const [q, setQ] = useState("");
  const [adding, setAdding] = useState(false);
  const query = useDebounced(q.trim(), 300);

  const clients = useInfiniteQuery({
    queryKey: [...getClientsListQueryKey(), query],
    initialPageParam: undefined as string | undefined,
    queryFn: ({ pageParam, signal }) => clientsList({ q: query || undefined, cursor: pageParam, limit: 50 }, { signal }),
    getNextPageParam: (last) => last.next_cursor ?? undefined,
  });
  const rows = clients.data?.pages.flatMap((p) => p.items) ?? [];

  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-3xl">{t("title")}</h1>
        {canWrite && (
          <Button onClick={() => setAdding(true)}>
            <Plus aria-hidden="true" /> {t("add")}
          </Button>
        )}
      </div>
      <div className="relative">
        <Search aria-hidden="true" className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          type="search"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={t("search")}
          aria-label={t("search")}
          className="h-11 pl-9"
        />
      </div>

      {clients.isPending ? (
        <Skeleton className="h-64 w-full" />
      ) : rows.length === 0 ? (
        <p className="rounded-lg border border-dashed bg-card px-4 py-10 text-center text-muted-foreground">
          {query ? t("noMatches", { q: query }) : t("empty")}
        </p>
      ) : (
        <ul className="divide-y rounded-lg border bg-card" aria-label={t("title")}>
          {rows.map((c) => (
            <li key={c.id}>
              <Link href={`/clients/${c.id}`} className="grid gap-0.5 px-4 py-3 hover:bg-accent sm:grid-cols-[minmax(0,2fr)_minmax(0,1.3fr)_minmax(0,1fr)] sm:items-center sm:gap-4">
                <span className="font-bold">
                  {c.display_name}
                  {c.kind === "corporate" && <span className="ml-2 text-sm font-normal text-muted-foreground">{t("corporate")}</span>}
                </span>
                <span className="tabular text-sm text-muted-foreground sm:text-base sm:text-foreground">{formatPhone(c.phone) ?? c.email ?? ""}</span>
                <span className="flex flex-wrap gap-1">
                  {c.tags.slice(0, 3).map((tag) => <Badge key={tag} variant="secondary">{tag}</Badge>)}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
      {clients.hasNextPage && (
        <div>
          <Button variant="outline" onClick={() => clients.fetchNextPage()} disabled={clients.isFetchingNextPage}>
            {t("loadMore")}
          </Button>
        </div>
      )}

      <Sheet open={adding} onOpenChange={setAdding}>
        <SheetContent className="w-full overflow-y-auto sm:max-w-xl">
          <SheetHeader>
            <SheetTitle>{t("add")}</SheetTitle>
            <SheetDescription className="sr-only">{t("add")}</SheetDescription>
          </SheetHeader>
          <div className="px-4 pb-8">
            <ClientForm
              submitLabel={t("save")}
              onSubmit={async (values) => {
                const created = await clientsCreate(toPayload(values));
                await queryClient.invalidateQueries({ queryKey: getClientsListQueryKey() });
                toast.success(t("created"));
                setAdding(false);
                router.push(`/clients/${created.id}`);
              }}
            />
          </div>
        </SheetContent>
      </Sheet>
    </div>
  );
}
