"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  getNotificationsListQueryKey,
  getNotificationsUnreadCountQueryKey,
  useNotificationsList,
  useNotificationsReadAll,
  useNotificationsUnreadCount,
} from "@/lib/api/generated/notifications/notifications";
import { relativeTime } from "@/lib/format";

export function NotificationBell() {
  const t = useTranslations("nav");
  const queryClient = useQueryClient();
  const unread = useNotificationsUnreadCount({ query: { refetchInterval: 60_000 } });
  const list = useNotificationsList({ limit: 10 });
  const readAll = useNotificationsReadAll({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: getNotificationsUnreadCountQueryKey() });
        void queryClient.invalidateQueries({ queryKey: getNotificationsListQueryKey() });
      },
    },
  });
  const count = unread.data?.unread ?? 0;
  const items = list.data?.items ?? [];

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="relative" aria-label={`${t("notifications")}${count ? ` (${count})` : ""}`}>
          <Bell className="size-5" />
          {count > 0 && (
            <span className="tabular absolute -top-0.5 -right-0.5 grid min-w-5 place-items-center rounded-full bg-maize px-1 text-xs font-bold text-ink">
              {count > 9 ? "9+" : count}
            </span>
          )}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <DropdownMenuLabel className="flex items-center justify-between">
          {t("notifications")}
          {count > 0 && (
            <button type="button" className="text-sm font-normal text-primary hover:underline" onClick={() => readAll.mutate()}>
              {t("markAllRead")}
            </button>
          )}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        {items.length === 0 ? (
          <p className="px-2 py-3 text-sm text-muted-foreground">{t("noNotifications")}</p>
        ) : (
          items.map((n) => (
            <DropdownMenuItem key={n.id} asChild className="grid gap-0.5 py-2">
              <Link href={n.link ?? "/"}>
                <span className={n.read_at ? "" : "font-bold"}>{n.title}</span>
                <span className="text-xs text-muted-foreground">{relativeTime(n.created_at)}</span>
              </Link>
            </DropdownMenuItem>
          ))
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
